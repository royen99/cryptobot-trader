
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

class Exchange(ABC):
    """
    Abstract adapter interface for any spot exchange.
    Implementations must be idempotent and network-safe.
    """
    name: str
    quote_currency: str

    @abstractmethod
    async def get_price(self, base_symbol: str) -> Optional[float]:
        """Return last price for base/quote pair, or None."""
        raise NotImplementedError

    @abstractmethod
    async def get_balances(self) -> Dict[str, float]:
        """Return mapping currency->available balance."""
        raise NotImplementedError

    @abstractmethod
    async def place_market_order(
        self,
        base_symbol: str,
        side: str,                         # "BUY" | "SELL"
        base_amount: Optional[float] = None,
        quote_amount: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any] | bool:
        """
        Place a market order. BUY should use quote_amount when possible;
        SELL should use base_amount. Returns order payload or False on failure.
        """
        raise NotImplementedError

    async def close(self) -> None:
        """Override to close network resources if needed."""
        return
