
from __future__ import annotations

import time, hmac, hashlib, asyncio
from collections import OrderedDict
from typing import Optional, Dict, Any
from urllib.parse import urlencode
from decimal import Decimal, ROUND_DOWN, getcontext
from .base import Exchange
from ..utils.http import get_http_session, jitter_backoff

getcontext().prec = 28

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

    async def _symbol_info(self, sym: str) -> dict:
        data = await self._request("GET", "/api/v3/exchangeInfo", params={"symbols": sym})
        if isinstance(data, dict) and data.get("symbols"):
            return data["symbols"][0]
        return {}

    async def _book_ticker(self, sym: str) -> dict:
        return await self._request("GET", "/api/v3/ticker/bookTicker", params={"symbol": sym})

    def _step_from_precision(self, p: str | int | float, default="0.00000001") -> Decimal:
        try:
            s = Decimal(str(p))
            # if p looks like a step (e.g. "0.0001"), keep it; if it's an int of decimals, convert
            if s == 0 or s == int(s):
                return Decimal("1") / (Decimal(10) ** int(s))
            return s
        except Exception:
            return Decimal(default)

    def _quantize(self, value: float, step: Decimal) -> str:
        v = Decimal(str(value))
        q = (v / step).to_integral_value(rounding=ROUND_DOWN) * step
        out = format(q, "f")
        return out.rstrip("0").rstrip(".") or "0"

    def _fmt_price(self, price: float, decimals: int = 8) -> str:
        s = f"{price:.{max(0, int(decimals))}f}"
        return s.rstrip("0").rstrip(".") or "0"

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
    async def get_balances(self) -> dict[str, float]:
        pairs = [("timestamp", str(self._ts())), ("recvWindow", "5000")]
        qs = urlencode(pairs, doseq=True)
        sig = self._sign(qs)
        params = OrderedDict(pairs + [("signature", sig)])
        data = await self._request("GET", "/api/v3/account", params=params, signed=True)
        out = {}
        try:
            for b in data.get("balances", []):
                ccy = b.get("asset")
                val = b.get("available") or b.get("free") or "0"
                out[ccy] = float(val)
        except Exception:
            pass
        return out

    # --- orders ---
    async def place_market_order(self, base_symbol: str, side: str,
                                base_amount: float | None = None,
                                quote_amount: float | None = None,
                                client_order_id: str | None = None) -> dict | bool:
        sym = f"{base_symbol}{self.quote_currency}"

        # helpers
        async def _symbol_info():
            data = await self._request("GET", "/api/v3/exchangeInfo", params={"symbols": sym})
            if isinstance(data, dict) and data.get("symbols"):
                return data["symbols"][0]
            return {}

        async def _book_ticker():
            return await self._request("GET", "/api/v3/ticker/bookTicker", params={"symbol": sym})

        def _step_from_precision(p, default="0.00000001"):
            try:
                d = Decimal(str(p))
                if d == 0 or d == int(d):
                    return Decimal("1") / (Decimal(10) ** int(d))
                return d
            except Exception:
                return Decimal(default)

        def _quantize(value: float, step: Decimal) -> str:
            v = Decimal(str(value))
            q = (v / step).to_integral_value(rounding=ROUND_DOWN) * step
            s = format(q, "f")
            return s.rstrip("0").rstrip(".") or "0"

        def _fmt_price(px: float, decimals: int = 8) -> str:
            s = f"{px:.{max(0, int(decimals))}f}"
            return s.rstrip("0").rstrip(".") or "0"

        def _signed_params(pairs: list[tuple[str, str]]) -> dict:
            # sign EXACTLY the encoded query we will send (no sorting)
            qs = urlencode(pairs, doseq=True)
            sig = self._sign(qs)
            pairs_with_sig = pairs + [("signature", sig)]
            # preserve insertion order
            return OrderedDict(pairs_with_sig)

        info = await _symbol_info()
        allowed = set(info.get("orderTypes", []))
        recv = "5000"

        # MARKET path
        if "MARKET" in allowed:
            if side.upper() == "BUY":
                if quote_amount is None:
                    return {"error": "quote_amount required for BUY"}
                pairs = [
                    ("symbol", sym),
                    ("side", side.upper()),
                    ("type", "MARKET"),
                    ("quoteOrderQty", f"{quote_amount:.2f}"),
                    ("newOrderRespType", "FULL"),
                    ("timestamp", str(self._ts())),
                    ("recvWindow", recv),
                ]
                if client_order_id:
                    pairs.insert(0, ("newClientOrderId", client_order_id))
                params = _signed_params(pairs)
                return await self._request("POST", "/api/v3/order", params=params, signed=True)

            else:
                if base_amount is None:
                    return {"error": "base_amount required for SELL"}
                qty = f"{base_amount:.8f}".rstrip("0").rstrip(".")
                pairs = [
                    ("symbol", sym),
                    ("side", side.upper()),
                    ("type", "MARKET"),
                    ("quantity", qty),
                    ("newOrderRespType", "FULL"),
                    ("timestamp", str(self._ts())),
                    ("recvWindow", recv),
                ]
                if client_order_id:
                    pairs.insert(0, ("newClientOrderId", client_order_id))
                params = _signed_params(pairs)
                return await self._request("POST", "/api/v3/order", params=params, signed=True)

        # LIMIT fallback (pair doesn’t allow MARKET)
        book = await _book_ticker()
        if not isinstance(book, dict) or "askPrice" not in book or "bidPrice" not in book:
            return {"error": "bookTicker unavailable", "symbol": sym}

        bid = float(book["bidPrice"]); ask = float(book["askPrice"])
        nudge_bps = 10  # 0.10% to push fill
        base_step = _step_from_precision(info.get("baseSizePrecision", "0.0001"))
        quote_dec = int(info.get("quotePrecision", 4))

        if side.upper() == "BUY":
            if quote_amount is None:
                return {"error": "quote_amount required for BUY"}
            px = ask * (1 + nudge_bps / 10_000)
            qty = float(Decimal(str(quote_amount)) / Decimal(str(px)))
            qty_str = _quantize(qty, base_step)
        else:
            if base_amount is None:
                return {"error": "base_amount required for SELL"}
            px = bid * (1 - nudge_bps / 10_000)
            qty_str = _quantize(base_amount, base_step)

        price_str = _fmt_price(px, quote_dec)
        pairs = [
            ("symbol", sym),
            ("side", side.upper()),
            ("type", "LIMIT"),
            ("price", price_str),
            ("quantity", qty_str),
            ("timestamp", str(self._ts())),
            ("recvWindow", recv),
        ]
        if client_order_id:
            pairs.insert(0, ("newClientOrderId", client_order_id))
        params = _signed_params(pairs)
        return await self._request("POST", "/api/v3/order", params=params, signed=True)

