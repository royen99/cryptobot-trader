# Coin Configuration Refactor Summary 🚀

## What Changed

Moved all coin-specific trading parameters from static JSON (`config.json`) to database (`coin_settings` table) for runtime reconfigurability.

---

## Files Modified

### Core Application
- **`app/main.py`**
  - Added `load_coins_config_from_db()` function to fetch coin settings from PostgreSQL
  - Moved DB connection parameters earlier in init sequence
  - Added fallback handling if `coin_settings` table is empty
  - Preserved exact dictionary structure expected by downstream code

### Configuration
- **`config.json.template`**
  - Deprecated `coins` section with migration notice
  - Kept all non-coin settings (API keys, global percentages, Telegram, DB connection)

### Database
- **`init_db.sql`**
  - Added `coin_settings` table schema
  - Included auto-update trigger for `updated_at` timestamp
  - Seeded ETH and XRP with default values matching old JSON

### Migration
- **`migrations/001_add_coin_settings.sql`**
  - Full migration script for existing databases
  - Idempotent `ON CONFLICT` seed data
  - Partial index for enabled coins

- **`migrations/validate_migration.sql`**
  - Post-migration validation queries
  - Checks table existence, data integrity, trigger setup

- **`migrations/README.md`**
  - Usage instructions
  - SQL examples for adding/updating coins
  - Rollback plan

### Documentation
- **`README.md`**
  - Updated installation section with DB-driven config notice
  - Revised coin options table to reference database
  - Deprecated `coins` in generic options

- **`CHANGES.md`**
  - Added entry for 19/11/2025 with refactor details

---

## Data Structure Mapping

### Old JSON Format
```json
{
  "coins": {
    "ETH": {
      "enabled": true,
      "buy_percentage": -3,
      "min_order_sizes": {
        "buy": 0.01,
        "sell": 0.0001
      },
      "precision": {
        "price": 2,
        "amount": 6
      },
      ...
    }
  }
}
```

### New Database Schema
```sql
CREATE TABLE coin_settings (
    symbol TEXT PRIMARY KEY,
    enabled BOOLEAN,
    buy_percentage REAL,
    min_order_buy REAL,      -- was min_order_sizes.buy
    min_order_sell REAL,     -- was min_order_sizes.sell
    precision_price INTEGER, -- was precision.price
    precision_amount INTEGER,-- was precision.amount
    ...
);
```

### Runtime Dictionary (In-Memory)
The `load_coins_config_from_db()` function reconstructs the original nested dict:
```python
coins_config = {
    "ETH": {
        "enabled": True,
        "buy_percentage": -3.0,
        "min_order_sizes": {
            "buy": 0.01,
            "sell": 0.0001
        },
        "precision": {
            "price": 2,
            "amount": 6
        },
        ...
    }
}
```

This preserves **100% backward compatibility** with existing code that accesses:
- `coins_config[symbol]["precision"]["price"]`
- `coins_config[symbol]["min_order_sizes"]["buy"]`
- etc.

---

## Type Conversions

The loader explicitly casts DB types to match expected Python types:

| DB Column | DB Type | Python Type | Cast |
|-----------|---------|-------------|------|
| `enabled` | BOOLEAN | bool | (none) |
| `buy_percentage` | REAL | float | `float()` |
| `volatility_window` | INTEGER | int | `int()` |
| `min_order_buy` | REAL | float | `float()` |
| `precision_price` | INTEGER | int | `int()` |

This prevents issues like `Decimal` objects from `psycopg2` breaking float arithmetic.

---

## Error Handling

### Empty Database
If `coin_settings` table is empty:
- Returns `{}` from loader
- `crypto_symbols` becomes empty list
- `price_history_maxlen` defaults to 200
- Bot prints warning but doesn't crash

### DB Connection Failure
If database is unreachable during startup:
- Loader catches exception, prints error
- Returns `{}` (empty config)
- Bot continues but won't trade (no enabled symbols)

### Future Enhancement
Consider adding a `/reload-config` endpoint to hot-swap settings without restart.

---

## Testing Checklist

- [x] Fresh install: `init_db.sql` creates table + seed data
- [x] Existing DB: Migration script adds table without breaking existing data
- [x] Loader produces correct nested dict structure
- [x] All `coins_config[symbol][...]` references work unchanged
- [x] Empty DB doesn't crash bot (fallback to default maxlen)
- [x] Type conversions prevent `Decimal` issues
- [x] Validation script confirms table/trigger/data integrity

---

## Migration Instructions (Quick Reference)

### Fresh Install
```bash
psql -h <host> -U <user> -d <db> -f init_db.sql
```

### Existing Database
```bash
psql -h <host> -U <user> -d <db> -f migrations/001_add_coin_settings.sql
psql -h <host> -U <user> -d <db> -f migrations/validate_migration.sql
```

### Add New Coin
```sql
INSERT INTO coin_settings (
    symbol, enabled, buy_percentage, sell_percentage, rebuy_discount,
    volatility_window, trend_window, macd_short_window, macd_long_window,
    macd_signal_window, rsi_period, trail_percent,
    min_order_buy, min_order_sell, precision_price, precision_amount
) VALUES (
    'BTC', TRUE, -2, 2, 2.5, 15, 50, 12, 26, 9, 14, 0.5,
    0.01, 0.00001, 2, 8
);
```

---

## Rollback Plan

If issues arise:

1. **Revert Code**
   ```bash
   git revert <commit-sha>
   ```

2. **Drop Table**
   ```sql
   DROP TABLE IF EXISTS coin_settings CASCADE;
   ```

3. **Restore JSON Config**
   - Uncomment `coins` section in `config.json.template`
   - Copy to `config.json`

---

## Future Improvements

1. **Hot Reload**: Add HTTP endpoint to refresh `coins_config` without restart
2. **Admin UI**: Web interface for coin management (because clicking > SQL 🖱️)
3. **Config Versioning**: Track changes in an audit table
4. **Strategy Presets**: Conservative/aggressive mode toggles per coin
5. **Coin Groups**: Enable/disable multiple coins atomically

---

## Notes

- **JSON Still Required**: API keys, Telegram tokens, DB connection stay in `config.json`
- **Backward Compat**: Code changes are drop-in; existing logic unchanged
- **Performance**: Single query at startup; no runtime DB overhead per cycle
- **Security**: DB credentials in `config.json` still need file permission lock (`0600`)

---

## Conclusion

This refactor transforms coin configuration from **static compile-time** to **dynamic runtime**, enabling:
- Quick threshold adjustments during volatile markets
- Coin rotation without code deploys
- Future admin tooling for non-technical users

**No functionality lost**, **no data migrated**, **100% backward compatible** 🎉

Let's yeet that container build cache! 🚀
