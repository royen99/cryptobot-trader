"""
Coinbase Advanced Trade API implementation 🪙
Handles all Coinbase-specific API calls and authentication.
"""

import jwt
import time
import secrets
import aiohttp
import asyncio
import random
from typing import Dict, Optional
from cryptography.hazmat.primitives import serialization
from aiohttp import ClientTimeout

from .base import BaseExchange


class CoinbaseExchange(BaseExchange):
    """Coinbase Advanced Trade API implementation."""

    # Network/Retry settings
    MAX_RETRIES = 5
    BASE_BACKOFF = 0.5  # seconds
    TIMEOUT = ClientTimeout(total=12, sock_connect=6, sock_read=6)

    def __init__(self, api_key: str, api_secret: str, request_host: str = "api.coinbase.com"):
        """
        Initialize Coinbase exchange client.
        
        Args:
            api_key: Coinbase API key name
            api_secret: Coinbase API private key (PEM format)
            request_host: API host (default: api.coinbase.com)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.request_host = request_host
        self._session: Optional[aiohttp.ClientSession] = None

    def get_platform_name(self) -> str:
        return "Coinbase"

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.TIMEOUT)
        return self._session

    async def _jitter_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter."""
        return self.BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 0.2)

    def _build_jwt(self, uri: str) -> str:
        """Generate JWT token for Coinbase API authentication."""
        private_key_bytes = self.api_secret.encode("utf-8")
        private_key = serialization.load_pem_private_key(private_key_bytes, password=None)

        jwt_payload = {
            "sub": self.api_key,
            "iss": "cdp",
            "nbf": int(time.time()),
            "exp": int(time.time()) + 120,
            "uri": uri,
        }

        jwt_token = jwt.encode(
            jwt_payload,
            private_key,
            algorithm="ES256",
            headers={"kid": self.api_key, "nonce": secrets.token_hex()},
        )

        return jwt_token if isinstance(jwt_token, str) else jwt_token.decode("utf-8")

    async def _api_request(self, method: str, path: str, body=None):
        """
        Resilient Coinbase API request with retries, backoff, and timeouts.
        Returns parsed JSON or None on persistent failure.
        """
        session = await self._get_session()
        uri = f"{method} {self.request_host}{path}"
        jwt_token = self._build_jwt(uri)

        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "CB-VERSION": "2024-02-05",
        }

        url = f"https://{self.request_host}{path}"
        last_err = None

        for attempt in range(self.MAX_RETRIES):
            try:
                async with session.request(method, url, headers=headers, json=body) as resp:
                    # Happy path
                    if 200 <= resp.status < 300:
                        return await (resp.json() if resp.content_type == "application/json" else resp.text())

                    # Rate limited
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait = float(retry_after) if retry_after else await self._jitter_backoff(attempt)
                        print(f"⏳ 429 Too Many Requests. Retrying after {wait:.2f}s (attempt {attempt+1}/{self.MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue

                    # Transient server errors
                    if resp.status >= 500:
                        wait = await self._jitter_backoff(attempt)
                        text = await resp.text()
                        print(f"⚠️ Server error {resp.status}: {text[:200]}... Retrying in {wait:.2f}s (attempt {attempt+1}/{self.MAX_RETRIES})")
                        await asyncio.sleep(wait)
                        continue

                    # Client errors (don't retry)
                    text = await resp.text()
                    print(f"❌ Coinbase API request failed: {resp.status} {text[:300]}")
                    return None

            except asyncio.CancelledError:
                raise
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_err = e
                wait = await self._jitter_backoff(attempt)
                print(f"🌐 Network/timeout error: {type(e).__name__}: {e}. Retrying in {wait:.2f}s (attempt {attempt+1}/{self.MAX_RETRIES})")
                await asyncio.sleep(wait)
            except Exception as e:
                last_err = e
                print(f"❗ Unexpected error during Coinbase API request: {e}")
                break

        print(f"🚫 Giving up after {self.MAX_RETRIES} attempts. Last error: {last_err}")
        return None

    async def get_price(self, symbol: str, quote_currency: str) -> Optional[float]:
        """Fetch cryptocurrency price from Coinbase."""
        data = await self._api_request("GET", f"/api/v3/brokerage/products/{symbol}-{quote_currency}")
        if not data:
            print(f"⚠️ Failed to fetch {symbol} price from Coinbase (no data).")
            return None

        try:
            if "price" in data:
                return float(data["price"])
            if "product" in data and "price" in data["product"]:
                return float(data["product"]["price"])
        except Exception as e:
            print(f"⚠️ Malformed price response for {symbol}: {e} -> {str(data)[:200]}")

        print(f"⚠️ Price not found in Coinbase response for {symbol}.")
        return None

    async def get_balances(self) -> Dict[str, float]:
        """Fetch balances from Coinbase."""
        path = "/api/v3/brokerage/accounts"
        data = await self._api_request("GET", path)

        balances = {}
        if data and "accounts" in data:
            for account in data["accounts"]:
                currency = account["currency"]
                available_balance = float(account["available_balance"]["value"])
                balances[currency] = available_balance

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
        """Place a buy/sell order on Coinbase."""
        path = "/api/v3/brokerage/orders"

        order_data = {
            "client_order_id": secrets.token_hex(16),
            "product_id": f"{symbol}-{quote_currency}",
            "side": side,
            "order_configuration": {
                "market_market_ioc": {}
            }
        }

        if side == "BUY":
            amount_precision = precision.get("amount", 6)
            quote_cost = round(current_price * amount, 2)

            if quote_cost < min_order_sizes["buy"]:
                print(f"🚫  - Buy order too small: ${quote_cost} (minimum: ${min_order_sizes['buy']})")
                return False

            rounded_amount = round(amount, amount_precision)
            order_data["order_configuration"]["market_market_ioc"]["quote_size"] = str(quote_cost)

        else:  # SELL
            amount_precision = precision["amount"]
            rounded_amount = round(amount, amount_precision)

            if rounded_amount < min_order_sizes["sell"]:
                print(f"🚫  - Sell order too small: {rounded_amount:.{amount_precision}f} {symbol} (minimum: {min_order_sizes['sell']:.{amount_precision}f} {symbol})")
                return False

            order_data["order_configuration"]["market_market_ioc"]["base_size"] = str(f"{rounded_amount:.{amount_precision}f}")
            print(f"🛠️  - Adjusted Sell Amount for {symbol}: {rounded_amount:.{amount_precision}f} (Precision: {amount_precision})")

        print(f"🛠️  - Placing {side} order for {symbol}: Amount = {rounded_amount}, Price = {current_price}")

        response = await self._api_request("POST", path, order_data)

        # Handle response
        if response and response.get("success", False):
            order_id = response["success_response"]["order_id"]
            print(f"✅  - {side.upper()} Order Placed for {symbol}: Order ID = {order_id}")
            return True
        else:
            print(f"❌  - Order Failed for {symbol}: {response.get('error', 'Unknown error') if response else 'No response'}")
            if response:
                print(f"🔄  - Raw Response: {response}")
            return False

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
