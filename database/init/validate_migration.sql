-- Validation script: Check coin_settings migration success
-- Run after applying 001_add_coin_settings.sql

-- 1. Verify table exists
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'coin_settings'
) AS table_exists;

-- 2. Count enabled coins (should be 2 for fresh install: ETH + XRP)
SELECT COUNT(*) AS enabled_coins 
FROM coin_settings 
WHERE enabled = TRUE;

-- 3. List all configured coins with key settings
SELECT 
    symbol,
    enabled,
    buy_percentage,
    sell_percentage,
    trend_window,
    min_order_buy,
    min_order_sell,
    precision_price,
    precision_amount
FROM coin_settings
ORDER BY symbol;

-- 4. Check for any missing critical fields (nulls shouldn't exist)
SELECT 
    symbol,
    CASE 
        WHEN buy_percentage IS NULL THEN 'Missing buy_percentage'
        WHEN sell_percentage IS NULL THEN 'Missing sell_percentage'
        WHEN min_order_buy IS NULL THEN 'Missing min_order_buy'
        WHEN min_order_sell IS NULL THEN 'Missing min_order_sell'
        ELSE 'OK'
    END AS validation_status
FROM coin_settings
WHERE buy_percentage IS NULL 
   OR sell_percentage IS NULL 
   OR min_order_buy IS NULL 
   OR min_order_sell IS NULL;

-- 5. Verify trigger exists (auto-update timestamp)
SELECT EXISTS (
    SELECT FROM pg_trigger 
    WHERE tgname = 'trg_coin_settings_update'
) AS trigger_exists;

-- Expected output:
-- table_exists: true
-- enabled_coins: 2
-- List shows ETH and XRP with proper settings
-- No rows in validation_status check (all OK)
-- trigger_exists: true

-- If everything looks good, you're ready to restart the trading bot! 🚀
