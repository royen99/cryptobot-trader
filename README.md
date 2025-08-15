# Cryptobot trader

Dockerized auto crypto-coin trader based on Coinbase (uses CoinBase's Advanced Trade API).

[![Docker Image Version (latest by date)](https://img.shields.io/docker/v/royen99/cryptobot-trader?logo=docker)](https://hub.docker.com/r/royen99/cryptobot-trader)
[![Docker Pulls](https://img.shields.io/docker/pulls/royen99/cryptobot-trader?logo=docker)](https://hub.docker.com/r/royen99/cryptobot-trader)
[![CI/CD](https://github.com/royen99/cryptobot-trader/actions/workflows/docker-publish.yml/badge.svg)](https://github.com/royen99/cryptobot-trader/actions/workflows/docker-publish.yml)
[![Stars](https://img.shields.io/github/stars/royen99/cryptobot-trader?logo=github)](https://github.com/royen99/cryptobot-trader)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

✅ Directly makes the API request (using JWT's).\
✅ Handles API responses & errors, printing available balances or errors properly.\
✅ Uses config.json for credentials, keeping them separate from the script. \
✅ Integrates with the [CryptoBot-Monitor](https://github.com/royen99/cryptobot-monitor) dashboard for real-time monitoring and alerts.

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

When adding coins to the `config.json` file, ensure you follow the same structure as the sample entries.
Each coin should have its own section with the necessary parameters.

Take care of the proper `precision` settings for each coin (`price` and `amount`).
When in doubt, you can check the Coinbase API documentation ([XRP Example](https://api.exchange.coinbase.com/currencies/XRP)) for the correct values.

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
`coins` | Configuration for each coin to trade.

### Coin specific options

Option | Description
--- | ---
`enabled` | Whether trading is enabled for this coin (default: true).
`trail_percent` | The percentage for the trailing stop (default: 1).
`buy_percentage` | The percentage of the account balance to use for buying (default: -4).
`sell_percentage` | The percentage of the coin balance to use for selling (default: 3).
`rebuy_discount` | The percentage discount for rebuying (default: 2).
`volatility_window` | The window size for calculating volatility (default: 20).
`trend_window` | The window size for calculating trend (default: 200).
`macd_short_window` | The short window size for MACD (default: 12).
`macd_long_window` | The long window size for MACD (default: 26).
`macd_signal_window` | The signal window size for MACD (default: 9).
`rsi_period` | The period for RSI calculation (default: 50).
`min_order_sizes` | The minimum order sizes for buying and selling.
`precision` | The precision settings for price and amount.

## Donations
If you find this project useful and would like to support its development, consider making a donation:

- BTC: `bc1qy5wu6vrxpclycl2y0wgnjjdxfd2qde7xemphgt`
- ETH: `0xe9128E8cc47bCab918292E2a0aE0C25971bb61EA`
- SOL: `ASwSbGHvcvebyPEUJRoE9aq3b2H2oJSaM7GsZAt83bjR`
- Via [CoinBase](https://commerce.coinbase.com/checkout/00370bad-7220-4115-b15f-cda931756c6a)
