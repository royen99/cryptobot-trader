# Cryptobot trader

Dockerized auto crypto-coin trader based on Coinbase (uses CoinBase's Advanced Trade API).

[![Docker Image Version (latest by date)](https://img.shields.io/docker/v/royen99/cryptobot-trader?logo=docker)](https://hub.docker.com/r/royen99/cryptobot-trader)
[![Docker Pulls](https://img.shields.io/docker/pulls/royen99/cryptobot-trader?logo=docker)](https://hub.docker.com/r/royen99/cryptobot-trader)
[![CI/CD](https://github.com/royen99/cryptobot-trader/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/royen99/cryptobot-trader/actions/workflows/docker-publish.yml)
[![Stars](https://img.shields.io/github/stars/royen99/cryptobot-trader?logo=github)](https://github.com/royen99/cryptobot-trader)
[![Multi-Arch Support](https://img.shields.io/badge/arch-linux%2Famd64%20%7C%20linux%2Farm64-blue?logo=docker)](https://hub.docker.com/r/royen99/cryptobot-trader/tags)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

✅ Directly makes the API request (using JWT's).\
✅ Handles API responses & errors, printing available balances or errors properly.\
✅ Uses config.json for credentials, keeping them separate from the script. \
✅ **Built-in Web Dashboard** for real-time monitoring, holdings tracking, and configuration management. \
✅ Integrates with the [CryptoBot-Monitor](https://github.com/royen99/cryptobot-monitor) dashboard for real-time monitoring and alerts. \
✅ Supports multiple cryptocurrencies with **database-driven settings** (runtime reconfigurable). \
✅ Telegram bot integration for notifications on buy/sell actions.

## How It Works

All scripts need at least a `config.json` file that has your Coinbase API credentials and a 

### Config Example (config.json)
```json
{
    "name": "organizations/{org_id}/apiKeys/{key_id}",
    "privateKey": "-----BEGIN EC PRIVATE KEY-----\nYOUR PRIVATE KEY\n-----END EC PRIVATE KEY-----\n"
}
```

See the `config.json.template` file for the full example (some scripts utilize additional settings).

**Ensure the `config.json` is securely stored** and not exposed in public repositories.

### Trade Logic

✅ Uses a PostgreSQL database backend for saving and loading price history and trading state.\
✅ Asynchronous API requests, improving performance and responsiveness.\
✅ Trades multiple cryptocurrencies with configurable settings.\
✅ Moving Average Convergence Divergence (MACD) to identify trend direction and momentum.\
✅ Relative Strength Index (RSI) to identify overbought and oversold conditions.\
✅ Integrated MACD and RSI signals into the trading strategy. \
✅ Inspects bollinger bands to determine price volatility and potential breakouts. \
✅ Calculates stochastic RSI indicator for additional momentum analysis. \
✅ Rebuy signals based on market conditions to reach dollar-cost averaging.

🚨 Note that the various indicators will only function with enough data points (depending on your settings).

Without enough price history you will see log lines such as:\
⚠️ LTC: Not enough data for indicators. Required: 51, Available: 46.\
⚠️ ETH: Not enough data for long-term MA. Skipping.

Example output:

```
🔍 Monitoring ETH... Initial Price: $2667.15
🔍 Monitoring XRP... Initial Price: $2.45
💰 Available Balances:
  - ETH: 61.07145081738762922
  - XRP: 630.2
  - SOL: 720.7
  - USDC: 310.3975527322856
📈 ETH Rising Streak: 6
🚀 ETH - Current Price: $4651.57 (1.81%), Peak Price: $4667.23, Trailing Stop Price: $4620.56
💔 ETH: Price is above Bollinger Upper Band ($4649.60) — sell signal!
📊  - ETH Avg buy price: None | Slope: 5.509999999999309 | Performance - Total Trades: 47 | Total Profit: $3108.05
📉 SOL Falling Streak: 1
🚀 SOL - Current Price: $195.13 (-2.43%), Peak Price: $198.20, Trailing Stop Price: $196.22
🔥 SOL Stochastic RSI Buy Signal: K = 0.18, D = 0.10
📊  - SOL Avg buy price: 192.33007217066984 | Slope: 0.09000000000000341 | Performance - Total Trades: 199 | Total Profit: $935.37
```

## Installation

### Quick Start with Dashboard 🚀

The easiest way to get started is using Docker Compose, which includes the trading bot, dashboard, and PostgreSQL:

```bash
# Copy the sample configuration
cp config.json.template config.json
# Edit config.json with your Coinbase API credentials

# Copy and customize docker-compose
cp docker-compose-sample.yml docker-compose.yml

# Start all services (trader + dashboard + database)
docker-compose up -d

# Access the dashboard at http://localhost:8000
```

**What you get:**
- Trading bot running in the background
- Web dashboard for monitoring and configuration
- PostgreSQL database with initialized schema
- All services networked together

### Alternative: Manual Setup

Prepare your PostgreSQL database by using the `init_db.sql` file. This will create the necessary tables and schema.

Use the supplied config.json.template file for your CoinBase API credentials, database connection settings, and other configurations. \
Make sure to rename it to `config.json` and fill in your details and place it in the appropriate directory. (.env by default)

1. Use the Docker Compose file to start the services:
   ```bash
   docker-compose -f docker-compose-sample.yml up -d
   ```

2. Run the Docker container directly:
   ```bash
   docker run -d --name cryptobot-trader royen99/cryptobot-trader
   ```

### 🆕 Database-Driven Coin Configuration

**Coin-specific settings have been moved to the database** for runtime reconfigurability without code restarts! 🚀

The `coins` section in `config.json` is now **deprecated**. All coin settings (buy/sell thresholds, windows, precision, etc.) are stored in the `coin_settings` table.

**Managing Coins:**
- View all: `SELECT * FROM coin_settings;`
- Enable/disable: `UPDATE coin_settings SET enabled = FALSE WHERE symbol = 'XRP';`
- Add new: See `migrations/README.md` for SQL examples
- Update thresholds: `UPDATE coin_settings SET buy_percentage = -4 WHERE symbol = 'ETH';`

Take care of the proper `precision` settings for each coin (`price` and `amount`).
When in doubt, you can check the Coinbase API documentation ([XRP Example](https://api.exchange.coinbase.com/currencies/XRP)) for the correct values.

## Web Dashboard 📊

The built-in dashboard provides a modern web interface for monitoring and controlling your trading bot:

**Features:**
- 💼 **Real-time Holdings**: Portfolio value, unrealized P&L, weighted average buy prices
- 📊 **Trade History**: Complete log of buy/sell executions with timestamps
- ⚙️ **Coin Settings Editor**: Adjust thresholds, windows, and precision on-the-fly
- 🎯 **Manual Trading**: Send immediate BUY/SELL commands to the bot
- 📈 **Performance Stats**: Total profit, trade counts, per-coin performance
- 🔄 **Auto-refresh**: Live updates every 30 seconds

**Access:** http://localhost:8000 (when using docker-compose)

**Documentation:** See [dashboard/README.md](dashboard/README.md) for detailed usage, API reference, and customization options.

## Pair with Cryptobot Monitor

The [Cryptobot Monitor](https://github.com/royen99/cryptobot-monitor) can be coupled with the trading bot to provide real-time monitoring and alerts based on market conditions. This allows for more informed trading decisions and the ability to react quickly to changing market dynamics.

It also features a web-based dashboard for visualizing trading performance, market trends, manual buy/sell actions, and more. \

### Example Cryptobot Monitor UI Screenshot
![Example UI Screenshot](https://github.com/royen99/cryptobot-monitor/blob/main/mainview.png?raw=true)

## Configuration options explained:

### Generic options

Option | Description
--- | ---
`name` | The name of the API key (e.g., `organizations/{org_id}/apiKeys/{key_id}`).
`privateKey` | The private key for the API key (must be kept secret).
`buy_percentage` | The percentage of the account balance to use for buying (default: 10).
`sell_percentage` | The percentage of the coin balance to use for selling (default: 100).
`buy_offset_percent` | The percentage offset for buy orders (default: -0.2).
`sell_offset_percent` | The percentage offset for sell orders (default: 0.2).
`trail_percent` | The percentage for the trailing stop (default: 1).
`telegram` | Telegram bot settings.
`database` | Database connection settings.
`coins` | ⚠️ **DEPRECATED** — Coin configuration moved to database (`coin_settings` table).

### Coin specific options (Database: `coin_settings` table)

Option | Description
--- | ---
`enabled` | Whether trading is enabled for this coin (default: true).
`trail_percent` | The percentage for the trailing stop (default: 0.5).
`buy_percentage` | The percentage threshold for buying (default: -3 for ETH).
`sell_percentage` | The percentage threshold for selling (default: 3 for ETH).
`rebuy_discount` | The percentage discount for rebuying (default: 2).
`volatility_window` | The window size for calculating volatility (default: 10).
`trend_window` | The window size for calculating trend (default: 26).
`macd_short_window` | The short window size for MACD (default: 12).
`macd_long_window` | The long window size for MACD (default: 26).
`macd_signal_window` | The signal window size for MACD (default: 9).
`rsi_period` | The period for RSI calculation (default: 14).
`min_order_buy` | The minimum buy order size in USDC (default: 0.01).
`min_order_sell` | The minimum sell order size in base coin (default varies).
`precision_price` | Price decimal places (default: 2).
`precision_amount` | Amount decimal places (default: 6).

**Note:** These settings are now stored in the database. Use SQL queries to modify them at runtime.

## Donations
If you find this project useful and would like to support its development, consider making a donation:

- BTC: `bc1qy5wu6vrxpclycl2y0wgnjjdxfd2qde7xemphgt`
- ETH: `0xe9128E8cc47bCab918292E2a0aE0C25971bb61EA`
- SOL: `ASwSbGHvcvebyPEUJRoE9aq3b2H2oJSaM7GsZAt83bjR`
- Via [CoinBase](https://commerce.coinbase.com/checkout/00370bad-7220-4115-b15f-cda931756c6a)
