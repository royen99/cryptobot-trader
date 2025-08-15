# Cryptobot trader

Dockerized auto crypto-coin trader based on Coinbase (uses CoinBase's Advanced Trade API).

## Features

✅ Directly makes the API request (using JWT's).\
✅ Handles API responses & errors, printing available balances or errors properly.\
✅ Uses config.json for credentials, keeping them separate from the script. \
✅ Integrates with the CryptoBot-Monitor dashboard for real-time monitoring and alerts.

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
✅ Concurrent Price Fetching. Fetches prices for all cryptocurrencies simultaneously.\
✅ Trades multiple cryptocurrencies with configurable settings.\
✅ Moving Average Convergence Divergence (MACD) to identify trend direction and momentum.\
✅ Relative Strength Index (RSI) to identify overbought and oversold conditions.\
✅ Integrated MACD and RSI signals into the trading strategy. \
✅ Inspects bollinger bands to determine price volatility and potential breakouts. \
✅ Calculates stochastic RSI indicator for additional momentum analysis.

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
📊  - ETH Avg buy price: None | Slope: 5.509999999999309 | Performance - Total Trades: 47 | Total Profit: $31.05
```
