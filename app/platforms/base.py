"""
Base exchange interface 🎯
Defines the common methods all exchange platforms must implement.
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class BaseExchange(ABC):
    """Abstract base class for all exchange platform implementations."""

    @abstractmethod
    async def get_price(self, symbol: str, quote_currency: str) -> Optional[float]:
        """Fetch the current price for a trading pair."""
        pass

    @abstractmethod
    async def get_balances(self) -> Dict[str, float]:
        """Fetch all account balances."""
        pass

    @abstractmethod
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
        """
        Place a market order (buy or sell).
        
        Args:
            symbol: Crypto symbol (e.g., "BTC", "ETH")
            side: "BUY" or "SELL"
            amount: Amount to trade
            current_price: Current market price
            quote_currency: Quote currency (e.g., "USDC")
            min_order_sizes: Minimum order sizes for buy/sell
            precision: Price and amount precision settings
            
        Returns:
            True if order placed successfully, False otherwise
        """
        pass

    @abstractmethod
    def get_platform_name(self) -> str:
        """Return the platform name (e.g., 'Coinbase', 'Binance')."""
        pass
