
from __future__ import annotations

import os, time, secrets, asyncio
import jwt
from typing import Optional, Dict, Any

from cryptography.hazmat.primitives import serialization
from .base import Exchange
from ..utils.http import get_http_session, jitter_backoff

class CoinbaseExchange(Exchange):
    """
    Coinbase Advanced Trade adapter.
    Uses JWT (ES256) per Coinbase 'cdp' scheme.
    """
    def __init__(self, name: str, private_key_pem: str, host: str = "api.coinbase.com", quote_currency: str = "USDC"):
        self.name = name
        self._private_key_pem = private_key_pem
        self.host = host
        self.quote_currency = quote_currency

    # --- auth ---
    def _build_jwt(self, method: str, path: str) -> str:
        uri = f"{method} {self.host}{path}"
        private_key = serialization.load_pem_private_key(self._private_key_pem.encode("utf-8"), password=None)
        payload = {
            "sub": self.name,
            "iss": "cdp",
            "nbf": int(time.time()),
            "exp": int(time.time()) + 120,
            "uri": uri,
        }
        token = jwt.encode(payload, private_key, algorithm="ES256", headers={"kid": self.name, "nonce": secrets.token_hex()})
        return token if isinstance(token, str) else token.decode("utf-8")

    async def _api_request(self, method: str, path: str, body: Any | None = None):
        session = await get_http_session()
        jwt_token = self._build_jwt(method, path)
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
            "CB-VERSION": "2024-02-05",
        }
        url = f"https://{self.host}{path}"
        last_err: Exception | None = None

        for attempt in range(5):
            try:
                async with session.request(method, url, headers=headers, json=body) as resp:
                    if 200 <= resp.status < 300:
                        if resp.content_type == "application/json":
                            return await resp.json()
                        return await resp.text()
                    if resp.status == 429:
                        retry_after = resp.headers.get("Retry-After")
                        wait = float(retry_after) if retry_after else await jitter_backoff(attempt)
                        await asyncio.sleep(wait); continue
                    if resp.status >= 500:
                        wait = await jitter_backoff(attempt)
                        await asyncio.sleep(wait); continue
                    # 4xx non-429
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
        data = await self._api_request("GET", f"/api/v3/brokerage/products/{base_symbol}-{self.quote_currency}")
        try:
            if not data: return None
            if isinstance(data, dict) and "price" in data: return float(data["price"])
            if "product" in data and "price" in data["product"]: return float(data["product"]["price"])
        except Exception:
            return None
        return None

    # --- account ---
    async def get_balances(self) -> Dict[str, float]:
        data = await self._api_request("GET", "/api/v3/brokerage/accounts")
        out: Dict[str, float] = {}
        try:
            for acct in data.get("accounts", []):
                ccy = acct["currency"]
                val = float(acct["available_balance"]["value"])
                out[ccy] = val
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
        path = "/api/v3/brokerage/orders"
        order = {
            "client_order_id": client_order_id or secrets.token_hex(16),
            "product_id": f"{base_symbol}-{self.quote_currency}",
            "side": side.upper(),
            "order_configuration": {
                "market_market_ioc": {}
            }
        }
        if side.upper() == "BUY":
            if quote_amount is None:
                return False
            order["order_configuration"]["market_market_ioc"]["quote_size"] = str(round(quote_amount, 2))
        else:
            if base_amount is None:
                return False
            order["order_configuration"]["market_market_ioc"]["base_size"] = f"{base_amount:.8f}".rstrip("0").rstrip(".")

        resp = await self._api_request("POST", path, order)
        if isinstance(resp, dict) and resp.get("success", False):
            return resp
        return False
