# Exchange Platform Abstraction 🚀

This directory contains the platform abstraction layer for supporting multiple cryptocurrency exchanges.

## Structure

- **`base.py`** - Abstract base class defining the exchange interface
- **`coinbase.py`** - Coinbase Advanced Trade API implementation
- **`__init__.py`** - Package exports

## Adding a New Exchange

To add support for a new exchange (e.g., Binance, Kraken):

1. Create a new file `<exchange_name>.py` in this directory
2. Implement the `BaseExchange` interface:
   ```python
   from .base import BaseExchange
   
   class BinanceExchange(BaseExchange):
       def __init__(self, api_key: str, api_secret: str):
           # Initialize your exchange client
           pass
       
       def get_platform_name(self) -> str:
           return "Binance"
       
       async def get_price(self, symbol: str, quote_currency: str):
           # Implement price fetching
           pass
       
       async def get_balances(self):
           # Implement balance fetching
           pass
       
       async def place_order(self, symbol, side, amount, current_price, quote_currency, min_order_sizes, precision):
           # Implement order placement
           pass
   ```

3. Export your new exchange in `__init__.py`:
   ```python
   from .binance import BinanceExchange
   __all__ = ["BaseExchange", "CoinbaseExchange", "BinanceExchange"]
   ```

4. Update `main.py` to allow selection between exchanges (via config or env var)

## Current Implementation

### Coinbase ✅
- **Authentication**: JWT with ES256 signing
- **API Version**: 2024-02-05
- **Rate Limiting**: Automatic retry with exponential backoff
- **Order Types**: Market IOC (Immediate or Cancel)
- **Quote Currency**: USDC

### Kraken ✅
- **Authentication**: HMAC-SHA512 with nonce
- **API Version**: v0
- **Rate Limiting**: Automatic retry with exponential backoff
- **Order Types**: Market orders
- **Pair Format**: Handles Kraken's special naming (BTC→XBT, etc.)
- **Quote Currency**: USDC (and others)

## Benefits of This Architecture

- ✅ **Extensibility** - Easy to add new exchanges without touching core bot logic
- ✅ **Maintainability** - Platform-specific code is isolated
- ✅ **Testability** - Can mock exchanges for testing
- ✅ **Flexibility** - Switch exchanges via configuration
- ✅ **Clean Code** - Single Responsibility Principle enforced
