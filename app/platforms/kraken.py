"""
Kraken Spot API implementation 🐙
Handles all Kraken-specific API calls and authentication.
"""

import hmac
import hashlib
import base64
import time
import urllib.parse
import aiohttp
import asyncio
import random
from typing import Dict, Optional
from aiohttp import ClientTimeout

from .base import BaseExchange


class KrakenExchange(BaseExchange):
    """Kraken Spot API implementation."""

    # Network/Retry settings
    MAX_RETRIES = 5
    BASE_BACKOFF = 0.5  # seconds
    TIMEOUT = ClientTimeout(total=15, sock_connect=8, sock_read=8)
    API_BASE = "https://api.kraken.com"

    def __init__(self, api_key: str, api_secret: str):
        """
        Initialize Kraken exchange client.
        
        Args:
            api_key: Kraken API key
            api_secret: Kraken API private key (base64 encoded)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self._session: Optional[aiohttp.ClientSession] = None

    def get_platform_name(self) -> str:
        return "Kraken"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.TIMEOUT)
        return self._session

    async def _jitter_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter."""
        return self.BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 0.2)

    def _generate_signature(self, urlpath: str, data: Dict, nonce: str) -> str:
        """
        Generate HMAC-SHA512 signature for Kraken API authentication.
        
        Kraken signature = HMAC-SHA512(urlpath + SHA256(nonce + postdata), base64_decoded_secret)
        """
        postdata = urllib.parse.urlencode(data)
        encoded = (nonce + postdata).encode()
        message = urlpath.encode() + hashlib.sha256(encoded).digest()

        signature = hmac.new(
            base64.b64decode(self.api_secret),
            message,
            hashlib.sha512
        )
        return base64.b64encode(signature.digest()).decode()

    async def _api_request(self, endpoint: str, data: Optional[Dict] = None, private: bool = False):
        """
        Make a request to Kraken API with retries and error handling.
        
        Args:
            endpoint: API endpoint (e.g., '/0/public/Ticker')
            data: POST data for private endpoints
            private: Whether this is a private (authenticated) endpoint
        """
        session = await self._get_session()
        url = f"{self.API_BASE}{endpoint}"
        headers = {"User-Agent": "CryptoBot/1.0"}
        
        if private:
            if data is None:
                data = {}
            nonce = str(int(time.time() * 1000))
            data["nonce"] = nonce
            
            signature = self._generate_signature(endpoint, data, nonce)
            headers["API-Key"] = self.api_key
            headers["API-Sign"] = signature

        last_err = None

        for attempt in range(self.MAX_RETRIES):
            try:
                if private or data:
                    # POST for private endpoints or when data is provided
                    async with session.post(url, data=data, headers=headers) as resp:
                        result = await self._handle_response(resp, attempt)
                        if result is not None:
                            return result
                else:
                    # GET for public endpoints
                    async with session.get(url, headers=headers) as resp:
                        result = await self._handle_response(resp, attempt)
                        if result is not None:
                            return result

            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                wait = await self._jitter_backoff(attempt)
                print(f"🌐 Network/timeout error: {type(e).__name__}: {e}. Retrying in {wait:.2f}s (attempt {attempt+1}/{self.MAX_RETRIES})")
                await asyncio.sleep(wait)
            except Exception as e:
                last_err = e
                print(f"❗ Unexpected error during Kraken API request: {e}")
                break

        print(f"🚫 Kraken API: Giving up after {self.MAX_RETRIES} attempts. Last error: {last_err}")
        return None

    async def _handle_response(self, resp: aiohttp.ClientResponse, attempt: int):
        """Handle API response with retries for transient errors."""
        if resp.status == 200:
            try:
                json_data = await resp.json()
                
                # Kraken returns {"error": [], "result": {...}}
                if json_data.get("error"):
                    errors = json_data["error"]
                    error_msg = ", ".join(errors)
                    print(f"❌ Kraken API error: {error_msg}")
                    
                    # Rate limit errors - retry with backoff
                    if any("rate limit" in e.lower() for e in errors):
                        wait = await self._jitter_backoff(attempt)
                        print(f"⏳ Rate limited. Retrying after {wait:.2f}s (attempt {attempt+1}/{self.MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        return None  # Signal retry
                    
                    return None  # Don't retry on other errors
                
                return json_data.get("result")
                
            except Exception as e:
                print(f"⚠️ Failed to parse Kraken response: {e}")
                return None

        # Server errors - retry
        if resp.status >= 500:
            wait = await self._jitter_backoff(attempt)
            text = await resp.text()
            print(f"⚠️ Kraken server error {resp.status}: {text[:200]}... Retrying in {wait:.2f}s (attempt {attempt+1}/{self.MAX_RETRIES})")
            await asyncio.sleep(wait)
            return None  # Signal retry

        # Client errors - don't retry
        text = await resp.text()
        print(f"❌ Kraken API request failed: {resp.status} {text[:300]}")
        return None

    def _format_pair(self, symbol: str, quote_currency: str) -> str:
        """
        Format trading pair for Kraken (e.g., BTC/USDC -> XBTUSDC).
        Kraken uses XXBT for BTC and other quirks.
        """
        # Kraken's special naming
        symbol_map = {
            "BTC": "XBT",
            "DOGE": "XDG",
        }
        
        base = symbol_map.get(symbol, symbol)
        quote = quote_currency
        
        # Kraken spot pairs are usually formatted as BASEQUOTE (no separator for major pairs)
        return f"{base}{quote}"

    async def get_price(self, symbol: str, quote_currency: str) -> Optional[float]:
        """Fetch cryptocurrency price from Kraken."""
        pair = self._format_pair(symbol, quote_currency)
        
        # Try with and without X prefix
        for pair_format in [pair, f"X{pair}"]:
            data = await self._api_request(
                "/0/public/Ticker",
                data={"pair": pair_format},
                private=False
            )
            
            if data:
                # Kraken returns a dict with pair name as key
                for pair_name, ticker_data in data.items():
                    try:
                        # 'c' = last trade closed array [price, lot volume]
                        last_price = float(ticker_data["c"][0])
                        print(f"📊 Kraken {symbol}/{quote_currency} (pair: {pair_name}): ${last_price}")
                        return last_price
                    except (KeyError, IndexError, ValueError) as e:
                        print(f"⚠️ Failed to parse Kraken price for {pair_format}: {e}")
                        continue

        print(f"⚠️ Failed to fetch {symbol}/{quote_currency} price from Kraken")
        return None

    async def get_balances(self) -> Dict[str, float]:
        """Fetch balances from Kraken."""
        data = await self._api_request("/0/private/Balance", private=True)
        
        balances = {}
        if data:
            for currency, balance in data.items():
                # Kraken prefixes currencies (XXBT, ZUSD, etc.)
                # Strip leading X or Z
                clean_currency = currency.lstrip("XZ")
                
                # Map back to standard names
                if clean_currency == "BT":
                    clean_currency = "BTC"
                elif clean_currency == "DG":
                    clean_currency = "DOGE"
                
                balances[clean_currency] = float(balance)
        
        return balances

    async def place_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        current_price: float,
        quote_currency: str,
        min_order_sizes: Dict[str, float],
        precision: Dict[str, int],
    ) -> bool:
        """Place a market order on Kraken."""
        pair = self._format_pair(symbol, quote_currency)
        
        # Kraken order types: market, limit, etc.
        order_data = {
            "pair": pair,
            "type": side.lower(),  # "buy" or "sell"
            "ordertype": "market",
        }

        if side == "BUY":
            amount_precision = precision.get("amount", 8)
            
            # For market buys, Kraken can use volume (amount) or quote amount
            # Using volume (base currency amount)
            rounded_amount = round(amount, amount_precision)
            
            # Check minimum order size (in quote currency)
            quote_cost = round(current_price * rounded_amount, 2)
            if quote_cost < min_order_sizes["buy"]:
                print(f"🚫 - Buy order too small: ${quote_cost} (minimum: ${min_order_sizes['buy']})")
                return False
            
            order_data["volume"] = str(rounded_amount)
            print(f"🛠️ - Kraken BUY: {rounded_amount:.{amount_precision}f} {symbol} (~${quote_cost:.2f})")

        else:  # SELL
            amount_precision = precision["amount"]
            rounded_amount = round(amount, amount_precision)

            if rounded_amount < min_order_sizes["sell"]:
                print(f"🚫 - Sell order too small: {rounded_amount:.{amount_precision}f} {symbol} (minimum: {min_order_sizes['sell']:.{amount_precision}f})")
                return False

            order_data["volume"] = str(rounded_amount)
            print(f"🛠️ - Kraken SELL: {rounded_amount:.{amount_precision}f} {symbol}")

        # Place the order
        response = await self._api_request("/0/private/AddOrder", data=order_data, private=True)

        if response:
            # Kraken returns {"descr": {...}, "txid": [...]}
            txids = response.get("txid", [])
            if txids:
                order_id = txids[0]
                print(f"✅ - {side.upper()} Order Placed on Kraken: Order ID = {order_id}")
                return True
            else:
                print(f"❌ - Kraken order response missing txid: {response}")
        else:
            print(f"❌ - Kraken order failed for {symbol}")

        return False

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
