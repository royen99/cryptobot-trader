"""
Platform abstraction layer for crypto exchanges 🚀
Allows the bot to work with multiple exchanges (Coinbase, Binance, Kraken, etc.)
"""

from .base import BaseExchange
from .coinbase import CoinbaseExchange
from .kraken import KrakenExchange

__all__ = ["BaseExchange", "CoinbaseExchange", "KrakenExchange"]
