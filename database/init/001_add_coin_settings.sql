-- Migration: Move coin-specific config from JSON to database
-- Purpose: Enable runtime reconfiguration without code restarts 🚀

-- Create coin_settings table
CREATE TABLE IF NOT EXISTS public.coin_settings (
    symbol TEXT PRIMARY KEY,
    enabled BOOLEAN DEFAULT TRUE,
    buy_percentage REAL NOT NULL,
    sell_percentage REAL NOT NULL,
    rebuy_discount REAL DEFAULT 2.0,
    volatility_window INTEGER DEFAULT 10,
    trend_window INTEGER DEFAULT 26,
    macd_short_window INTEGER DEFAULT 12,
    macd_long_window INTEGER DEFAULT 26,
    macd_signal_window INTEGER DEFAULT 9,
    rsi_period INTEGER DEFAULT 14,
    trail_percent REAL DEFAULT 0.5,
    min_order_buy REAL NOT NULL,
    min_order_sell REAL NOT NULL,
    precision_price INTEGER DEFAULT 2,
    precision_amount INTEGER DEFAULT 6,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Seed data from coins.json (21 coins total 🪙)
INSERT INTO public.coin_settings (
    symbol, enabled, buy_percentage, sell_percentage, rebuy_discount,
    volatility_window, trend_window, macd_short_window, macd_long_window,
    macd_signal_window, rsi_period, trail_percent,
    min_order_buy, min_order_sell, precision_price, precision_amount
) VALUES
    ('AAVE', TRUE, -4, 4, 2, 20, 200, 12, 26, 9, 50, 0.5, 4, 0.001, 2, 3),
    ('AVAX', TRUE, -3, 3, 2, 20, 200, 12, 26, 9, 50, 1, 4, 0.1, 2, 2),
    ('BONK', TRUE, -4.5, 4, 2, 20, 200, 12, 26, 9, 50, 1, 5, 100, 8, 0),
    ('CRO', TRUE, -5.5, 7, 2, 20, 200, 12, 26, 9, 50, 0.5, 2, 1, 4, 1),
    ('ETH', TRUE, -3, 4, 2, 20, 200, 12, 26, 9, 50, 1, 3, 0.0001, 2, 6),
    ('FET', TRUE, -4.8, 4, 2, 20, 200, 12, 26, 9, 50, 0.5, 2, 0.001, 3, 1),
    ('GODS', TRUE, -4.5, 3, 4, 20, 200, 12, 26, 9, 50, 1, 5, 0.01, 5, 1),
    ('HBAR', TRUE, -3, 3, 2, 20, 200, 12, 26, 9, 50, 1, 5, 0.1, 5, 1),
    ('LINK', TRUE, -4, 4, 2, 20, 200, 12, 26, 9, 50, 0.5, 4, 0.1, 2, 2),
    ('LTC', TRUE, -3, 3, 2, 20, 200, 12, 26, 9, 50, 1, 5, 0.01, 2, 8),
    ('ONDO', TRUE, -4, 4, 2, 20, 200, 12, 26, 9, 50, 1, 10, 0.1, 6, 2),
    ('PEPE', TRUE, -4, 3, 2, 20, 200, 12, 26, 9, 50, 0.5, 2, 1, 8, 0),
    ('RENDER', TRUE, -3, 2, 4, 20, 200, 12, 26, 9, 50, 1, 2, 0.1, 2, 2),
    ('SEI', TRUE, -3, 4, 4, 20, 200, 12, 26, 9, 50, 1, 5, 0.1, 5, 1),
    ('SHIB', TRUE, -4, 4, 4, 20, 200, 12, 26, 9, 50, 1, 4, 1, 8, 0),
    ('SOL', TRUE, -4, 4, 2, 20, 200, 12, 26, 9, 28, 1, 1, 0.001, 2, 8),
    ('SUI', TRUE, -3, 4, 2, 20, 200, 12, 26, 9, 28, 0.5, 1, 0.2, 4, 1),
    ('UNI', TRUE, -4, 4, 4, 20, 200, 12, 26, 9, 50, 0.5, 2, 0.2, 3, 3),
    ('XCN', TRUE, -8, 2, 2, 20, 200, 12, 26, 9, 50, 1, 5, 10, 5, 1),
    ('XLM', TRUE, -3, 3, 3, 20, 200, 12, 26, 9, 50, 1, 2, 1, 4, 6),
    ('XRP', TRUE, -3, 4, 2, 20, 200, 12, 26, 9, 50, 0.5, 2, 1, 4, 6)
ON CONFLICT (symbol) DO UPDATE SET
    enabled = EXCLUDED.enabled,
    buy_percentage = EXCLUDED.buy_percentage,
    sell_percentage = EXCLUDED.sell_percentage,
    rebuy_discount = EXCLUDED.rebuy_discount,
    volatility_window = EXCLUDED.volatility_window,
    trend_window = EXCLUDED.trend_window,
    macd_short_window = EXCLUDED.macd_short_window,
    macd_long_window = EXCLUDED.macd_long_window,
    macd_signal_window = EXCLUDED.macd_signal_window,
    rsi_period = EXCLUDED.rsi_period,
    trail_percent = EXCLUDED.trail_percent,
    min_order_buy = EXCLUDED.min_order_buy,
    min_order_sell = EXCLUDED.min_order_sell,
    precision_price = EXCLUDED.precision_price,
    precision_amount = EXCLUDED.precision_amount,
    updated_at = CURRENT_TIMESTAMP;

-- Index for quick enabled coin lookups
CREATE INDEX IF NOT EXISTS idx_coin_settings_enabled ON public.coin_settings (enabled) WHERE enabled = TRUE;

-- Trigger to auto-update updated_at timestamp (because YAML never lies 😜)
CREATE OR REPLACE FUNCTION update_coin_settings_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_coin_settings_update
BEFORE UPDATE ON public.coin_settings
FOR EACH ROW
EXECUTE FUNCTION update_coin_settings_timestamp();

-- Comment for future devs
COMMENT ON TABLE public.coin_settings IS 'Per-coin trading parameters — tweak at runtime without restarting the bot 🤖';
