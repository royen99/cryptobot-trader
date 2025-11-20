# Quick Migration Guide: JSON → Database Config 🚀

## TL;DR
Coin settings moved from `config.json` to database. Run migration SQL, restart bot, you're done.

---

## For Existing Users (Have Running Bot)

### Step 1: Backup Your Current Config
```bash
cp config.json config.json.backup
```

### Step 2: Run Migration Script
```bash
# Connect to your PostgreSQL database
psql -h your-db-host -U your-db-user -d your-db-name -f migrations/001_add_coin_settings.sql
```

### Step 3: Verify Migration
```bash
psql -h your-db-host -U your-db-user -d your-db-name -f migrations/validate_migration.sql
```

Expected output:
- `table_exists: t` (true)
- `enabled_coins: 2` (or however many you have)
- List of your coins with settings

### Step 4: Customize Your Coins (Optional)
If your JSON had custom settings different from ETH/XRP defaults:

```sql
-- Example: Update BTC settings to match your old config.json
UPDATE coin_settings 
SET buy_percentage = -2.5, 
    sell_percentage = 3.5,
    trend_window = 100
WHERE symbol = 'BTC';
```

### Step 5: Clean Up config.json (Optional but Recommended)
Remove the `coins` section from your `config.json`:

```json
{
  "name": "organizations/...",
  "privateKey": "...",
  "buy_percentage": 10,
  "sell_percentage": 10,
  "_comment": "Coin settings now in database - see migrations/README.md"
}
```

### Step 6: Restart Bot
```bash
docker-compose restart cryptobot-trader
# OR
docker restart cryptobot-trader
```

### Step 7: Monitor Logs
Check that coins load successfully:
```bash
docker logs -f cryptobot-trader
```

You should see:
```
🔍 Monitoring ETH... Initial Price: $...
🔍 Monitoring XRP... Initial Price: $...
```

---

## For New Users (Fresh Install)

Just use the standard `init_db.sql` — it now includes `coin_settings` with ETH/XRP defaults:

```bash
psql -h your-db-host -U your-db-user -d your-db-name -f init_db.sql
```

Then start the bot:
```bash
docker-compose up -d
```

---

## Adding a New Coin

### Option 1: SQL Insert
```sql
INSERT INTO coin_settings (
    symbol, enabled, buy_percentage, sell_percentage, rebuy_discount,
    volatility_window, trend_window, macd_short_window, macd_long_window,
    macd_signal_window, rsi_period, trail_percent,
    min_order_buy, min_order_sell, precision_price, precision_amount
) VALUES (
    'SOL',        -- Symbol
    TRUE,         -- Enabled
    -4,           -- Buy threshold %
    4,            -- Sell threshold %
    2,            -- Rebuy discount %
    15,           -- Volatility window
    50,           -- Trend window (moving avg)
    12, 26, 9,    -- MACD windows
    14,           -- RSI period
    0.5,          -- Trailing stop %
    0.01,         -- Min buy order (USDC)
    0.01,         -- Min sell order (base coin)
    2,            -- Price decimals
    6             -- Amount decimals
);
```

### Option 2: Copy Existing Coin Template
```sql
INSERT INTO coin_settings 
SELECT 'SOL', * 
FROM coin_settings 
WHERE symbol = 'ETH';
```

Then customize:
```sql
UPDATE coin_settings 
SET buy_percentage = -5, 
    min_order_sell = 0.001 
WHERE symbol = 'SOL';
```

**Note:** Check Coinbase API docs for correct precision values for your coin.

---

## Tweaking Live Settings

### Adjust Buy/Sell Thresholds
```sql
-- Make ETH more aggressive
UPDATE coin_settings 
SET buy_percentage = -5, sell_percentage = 5 
WHERE symbol = 'ETH';
```

### Disable Coin Temporarily
```sql
UPDATE coin_settings 
SET enabled = FALSE 
WHERE symbol = 'XRP';
```

### Re-enable Coin
```sql
UPDATE coin_settings 
SET enabled = TRUE 
WHERE symbol = 'XRP';
```

**Important:** Changes take effect on next bot restart (or implement hot-reload in future).

---

## Troubleshooting

### Bot Won't Start After Migration
**Symptom:** Bot crashes on startup with DB error

**Fix:** Check migration applied successfully:
```sql
SELECT COUNT(*) FROM coin_settings;
-- Should return > 0
```

If table doesn't exist:
```bash
psql ... -f migrations/001_add_coin_settings.sql
```

---

### No Coins Trading
**Symptom:** Bot starts but logs "No coins configured"

**Fix:** Check enabled coins:
```sql
SELECT symbol, enabled FROM coin_settings;
```

Enable at least one:
```sql
UPDATE coin_settings SET enabled = TRUE WHERE symbol = 'ETH';
```

---

### Bot Ignores My JSON Coin Settings
**Expected Behavior:** The `coins` section in `config.json` is now **deprecated**. All coin config must be in the database.

**Fix:** Migrate your JSON settings to database using SQL `INSERT`/`UPDATE` statements.

---

## Quick Reference

| Task | Command |
|------|---------|
| View all coins | `SELECT * FROM coin_settings;` |
| Enable coin | `UPDATE coin_settings SET enabled = TRUE WHERE symbol = 'BTC';` |
| Disable coin | `UPDATE coin_settings SET enabled = FALSE WHERE symbol = 'BTC';` |
| Add new coin | See "Adding a New Coin" section above |
| Update threshold | `UPDATE coin_settings SET buy_percentage = -3 WHERE symbol = 'ETH';` |
| Check precision | `SELECT symbol, precision_price, precision_amount FROM coin_settings;` |

---

## Getting Help

- Check `migrations/README.md` for detailed examples
- Review `docs/coin_config_refactor.md` for technical details
- Run `migrations/validate_migration.sql` to diagnose issues

Happy trading! 🚀
