
from __future__ import annotations
from typing import Any
from .base import Exchange
from .coinbase import CoinbaseExchange
from .mexc import MEXCExchange

def create_exchange(exchange_cfg: dict[str, Any]) -> Exchange:
    """
    Factory: exchange_cfg example:
    {"name":"coinbase","key_name":"...","private_key":"...","host":"api.coinbase.com","quote_currency":"USDC"}
    or
    {"name":"mexc","api_key":"...","secret_key":"...","quote_currency":"USDT"}
    """
    name = exchange_cfg.get("name", "").lower()
    if name == "coinbase":
        return CoinbaseExchange(
            name=exchange_cfg.get("key_name",""),
            private_key_pem=exchange_cfg["private_key"],
            host=exchange_cfg.get("host","api.coinbase.com"),
            quote_currency=exchange_cfg.get("quote_currency", "USDC"),
        )
    if name == "mexc":
        return MEXCExchange(
            api_key=exchange_cfg["api_key"],
            secret_key=exchange_cfg["secret_key"],
            quote_currency=exchange_cfg.get("quote_currency", "USDT"),
            base_url=exchange_cfg.get("base_url", "https://api.mexc.com"),
        )
    raise ValueError(f"Unknown exchange name: {name}")
