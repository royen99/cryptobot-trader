# Database Migrations 🗄️

## Overview
This directory contains SQL migrations to evolve the trading bot schema. Because YAML never lies 😜, we've moved coin-specific configuration from JSON into the database for runtime reconfigurability without code restarts.

---

## Migration: `001_add_coin_settings.sql`

### What Changed
- **Added Table**: `coin_settings` stores all per-coin trading parameters (thresholds, windows, precision, etc.)
- **Deprecated**: `coins` section in `config.json` → now database-driven
- **Benefits**:
  - Tweak buy/sell thresholds without restarting the bot
  - Add new coins via SQL `INSERT` (or future admin UI)
  - Audit config changes with `updated_at` timestamps
  - Disable coins temporarily without code changes

### Schema Details
```sql
CREATE TABLE coin_settings (
    symbol TEXT PRIMARY KEY,
    enabled BOOLEAN,
    buy_percentage REAL,
    sell_percentage REAL,
    rebuy_discount REAL,
    volatility_window INTEGER,
    trend_window INTEGER,
    macd_short_window INTEGER,
    macd_long_window INTEGER,
    macd_signal_window INTEGER,
    rsi_period INTEGER,
    trail_percent REAL,
    min_order_buy REAL,
    min_order_sell REAL,
    precision_price INTEGER,
    precision_amount INTEGER,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### How to Apply

#### For Fresh Installs
Just run the standard `init_db.sql` — it now includes `coin_settings` with ETH/XRP defaults.

```bash
psql -h <host> -U <user> -d <db> -f init_db.sql
```

#### For Existing Databases
Run the migration to add the new table + seed data:

```bash
psql -h <host> -U <user> -d <db> -f migrations/001_add_coin_settings.sql
```

**⚠️ Important**: After migration, your old JSON `coins` section is ignored. All coin config now lives in the database.

---

## Managing Coin Settings

### View All Coins
```sql
SELECT symbol, enabled, buy_percentage, sell_percentage 
FROM coin_settings;
```

### Enable/Disable a Coin
```sql
UPDATE coin_settings 
SET enabled = FALSE 
WHERE symbol = 'XRP';
```

### Add a New Coin
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

### Update Thresholds (Runtime Tweak)
```sql
UPDATE coin_settings 
SET buy_percentage = -4, sell_percentage = 4 
WHERE symbol = 'ETH';
```

The bot will pick up changes on the **next restart** (or add a config reload endpoint for hot-swapping).

---

## Rollback Plan
If you need to revert:

1. Drop the new table:
   ```sql
   DROP TABLE IF EXISTS coin_settings CASCADE;
   ```

2. Restore the `coins` section in your `config.json` from the template.

3. Revert `main.py` to load from `config.get("coins", {})`.

---

## Future Enhancements
- Add a `/reload-config` HTTP endpoint for live updates without restart
- Build a simple admin UI for coin management (because clicking beats SQL 🖱️)
- Track config changes in an audit log table
- Per-coin strategy presets (conservative/aggressive modes)

Happy trading! 🚀
