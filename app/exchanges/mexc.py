
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

    def _signed_params(self, pairs: list[tuple[str, str]]) -> OrderedDict:
        qs = urlencode(pairs, doseq=True)           # EXACT string we'll send
        sig = self._sign(qs)
        return OrderedDict(pairs + [("signature", sig)])

    async def _symbol_info(self, sym: str) -> dict:
        data = await self._request("GET", "/api/v3/exchangeInfo", params={"symbols": sym})
        if isinstance(data, dict) and data.get("symbols"):
            return data["symbols"][0]
        return {}

    async def _book_ticker(self, sym: str) -> dict:
        return await self._request("GET", "/api/v3/ticker/bookTicker", params={"symbol": sym})

    async def _query_order(self, sym: str, order_id: str) -> dict:
        pairs = [("symbol", sym), ("orderId", order_id), ("timestamp", str(self._ts())), ("recvWindow", "5000")]
        params = self._signed_params(pairs)
        return await self._request("GET", "/api/v3/order", params=params, signed=True)

    def _step_from_precision(self, p, default="0.00000001"):
        try:
            d = Decimal(str(p))
            if d == 0 or d == int(d):
                return Decimal("1") / (Decimal(10) ** int(d))
            return d
        except Exception:
            return Decimal(default)

    def _quantize(self, value: float, step: Decimal) -> str:
        v = Decimal(str(value))
        q = (v / step).to_integral_value(rounding=ROUND_DOWN) * step
        s = format(q, "f")
        return s.rstrip("0").rstrip(".") or "0"

    def _fmt_price(self, px: float, decimals: int = 8) -> str:
        s = f"{px:.{max(0, int(decimals))}f}"
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
    async def place_market_order(self, base_symbol: str, side: str,
                                base_amount: float | None = None,
                                quote_amount: float | None = None,
                                client_order_id: str | None = None) -> dict | bool:
        sym = f"{base_symbol}{self.quote_currency}"
        info = await self._symbol_info(sym)
        allowed = set(info.get("orderTypes", []))
        recv = "5000"

        # helper to send signed POST /order
        async def _send(pairs: list[tuple[str, str]]) -> dict:
            pairs += [("timestamp", str(self._ts())), ("recvWindow", recv)]
            if client_order_id:
                pairs.insert(0, ("newClientOrderId", client_order_id))
            params = self._signed_params(pairs)
            return await self._request("POST", "/api/v3/order", params=params, signed=True)

        # Try MARKET if allowed
        if "MARKET" in allowed:
            if side.upper() == "BUY":
                if quote_amount is None:
                    return {"ok": False, "error": "quote_amount required for BUY"}
                resp = await _send([
                    ("symbol", sym), ("side", side.upper()), ("type", "MARKET"),
                    ("quoteOrderQty", f"{quote_amount:.2f}"),
                    ("newOrderRespType", "FULL"),
                ])
            else:
                if base_amount is None:
                    return {"ok": False, "error": "base_amount required for SELL"}
                qty = f"{base_amount:.8f}".rstrip("0").rstrip(".")
                resp = await _send([
                    ("symbol", sym), ("side", side.upper()), ("type", "MARKET"),
                    ("quantity", qty),
                    ("newOrderRespType", "FULL"),
                ])

            if isinstance(resp, dict) and "code" not in resp:
                q, px = self._extract_fill(resp)
                if q and px:
                    return {"ok": True, "base_qty": q, "avg_px": px, "raw": resp}
            return {"ok": False, "error": resp, "raw": resp}

        # Fallback: LIMIT IOC near book
        book = await self._book_ticker(sym)
        if not isinstance(book, dict) or "askPrice" not in book or "bidPrice" not in book:
            return {"ok": False, "error": "bookTicker unavailable", "symbol": sym}

        bid = float(book["bidPrice"]); ask = float(book["askPrice"])
        nudge_bps = 10  # 0.10%
        base_step = self._step_from_precision(info.get("baseSizePrecision", "0.0001"))
        quote_dec = int(info.get("quotePrecision", 4))

        if side.upper() == "BUY":
            if quote_amount is None:
                return {"ok": False, "error": "quote_amount required for BUY"}
            px = ask * (1 + nudge_bps / 10_000)
            qty = float(Decimal(str(quote_amount)) / Decimal(str(px)))
            qty_str = self._quantize(qty, base_step)
            price_str = self._fmt_price(px, quote_dec)
        else:
            if base_amount is None:
                return {"ok": False, "error": "base_amount required for SELL"}
            px = bid * (1 - nudge_bps / 10_000)
            qty_str = self._quantize(base_amount, base_step)
            price_str = self._fmt_price(px, quote_dec)

        resp = await _send([
            ("symbol", sym), ("side", side.upper()), ("type", "LIMIT"),
            ("timeInForce", "IOC"),
            ("price", price_str), ("quantity", qty_str),
        ])

        # Try to resolve fill (IOC should fill immediately, else query once)
        if isinstance(resp, dict) and "orderId" in resp:
            q, px = self._extract_fill(resp)
            if not (q and px):
                # query once (fills often settle right after)
                oq = await self._query_order(sym, str(resp["orderId"]))
                q, px = self._extract_fill(oq)
            if q and px:
                return {"ok": True, "base_qty": q, "avg_px": px, "raw": resp}

        return {"ok": False, "error": resp, "raw": resp}
