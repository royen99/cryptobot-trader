
from __future__ import annotations

import time, hmac, hashlib, asyncio
from typing import Optional, Dict, Any
from urllib.parse import urlencode

from .base import Exchange
from ..utils.http import get_http_session, jitter_backoff

class MEXCExchange(Exchange):
    """
    MEXC Spot v3 adapter.
    Auth: HMAC SHA256 over totalParams with secretKey; send 'timestamp' (ms) and 'signature'.
    Header: X-MEXC-APIKEY
    Base URL: https://api.mexc.com
    Quote default: Use quote_currency from config, default USDT
    """
    def __init__(self, api_key: str, secret_key: str, quote_currency: str, base_url: str = "https://api.mexc.com"):
        self.name = "mexc"
        self.api_key = api_key
        self.secret_key = secret_key.encode("utf-8")
        self.quote_currency = quote_currency
        self.base_url = base_url

    # --- signing helpers ---
    def _ts(self) -> int:
        return int(time.time() * 1000)

    def _sign(self, params_str: str) -> str:
        return hmac.new(self.secret_key, params_str.encode("utf-8"), hashlib.sha256).hexdigest()

    async def _request(self, method: str, path: str, params: Dict[str, Any] | None = None, signed: bool = False, json_body: Dict[str, Any] | None = None):
        session = await get_http_session()
        headers = {"Content-Type": "application/json"}
        if signed:
            headers["X-MEXC-APIKEY"] = self.api_key

        query = ""
        body = None

        if params:
            # We prefer query-string for both GET/POST/DELETE to match MEXC examples
            query = "?" + urlencode(params, doseq=True)
        else:
            body = json_body

        url = f"{self.base_url}{path}{query}"
        last_err: Exception | None = None

        for attempt in range(5):
            try:
                async with session.request(method, url, headers=headers, json=body) as resp:
                    if 200 <= resp.status < 300:
                        if resp.content_type == "application/json":
                            return await resp.json()
                        return await resp.text()
                    if resp.status == 429:
                        wait = await jitter_backoff(attempt)
                        await asyncio.sleep(wait); continue
                    if resp.status >= 500:
                        wait = await jitter_backoff(attempt)
                        await asyncio.sleep(wait); continue
                    try:
                        txt = await resp.text()
                    except Exception:
                        txt = f"HTTP {resp.status}"
                    return {"error": txt, "status": resp.status}
            except asyncio.CancelledError:
                raise
            except Exception as e:
                last_err = e
                await asyncio.sleep(await jitter_backoff(attempt))
        return {"error": f"network_error:{last_err}"}

    # --- public ---
    async def get_price(self, base_symbol: str) -> Optional[float]:
        sym = f"{base_symbol}{self.quote_currency}"
        data = await self._request("GET", "/api/v3/ticker/price", params={"symbol": sym})
        if isinstance(data, dict) and "price" in data:
            try:
                return float(data["price"])
            except Exception:
                return None
        return None

    # --- account ---
    async def get_balances(self) -> Dict[str, float]:
        # Signed GET /api/v3/account with timestamp and signature
        params = {"timestamp": self._ts()}
        total_params = urlencode(params)
        sig = self._sign(total_params)

        # For signed GET, send signature & timestamp as query
        data = await self._request("GET", "/api/v3/account", params={**params, "signature": sig}, signed=True)
        out: Dict[str, float] = {}
        try:
            for b in data.get("balances", []):
                ccy = b.get("asset")
                # prefer 'available', fall back to 'free'
                val = b.get("available") or b.get("free") or "0"
                out[ccy] = float(val)
        except Exception:
            pass
        return out

    # --- orders ---
    async def place_market_order(
        self,
        base_symbol: str,
        side: str,
        base_amount: float | None = None,
        quote_amount: float | None = None,
        client_order_id: str | None = None,
    ) -> Dict[str, Any] | bool:
        # POST /api/v3/order with HMAC signature
        sym = f"{base_symbol}{self.quote_currency}"
        body: Dict[str, Any] = {
            "symbol": sym,
            "side": side.upper(),
            "type": "MARKET",
            "timestamp": self._ts(),
        }
        if client_order_id:
            body["newClientOrderId"] = client_order_id

        if side.upper() == "BUY":
            if quote_amount is None:
                return False
            body["quoteOrderQty"] = str(round(quote_amount, 2))
        else:
            if base_amount is None:
                return False
            body["quantity"] = f"{base_amount:.8f}".rstrip("0").rstrip(".")

        # signature is over totalParams (query+body). We are sending all fields in body, so sign the x-www-form-urlencoded style.
        to_sign = "&".join([f"{k}={body[k]}" for k in sorted(body.keys())])
        sig = self._sign(to_sign)
        body["signature"] = sig

        resp = await self._request("POST", "/api/v3/order", params=body, signed=True)
        if isinstance(resp, dict) and ("orderId" in resp or resp.get("code") == 0 or resp.get("symbol")):
            return resp
        return False
