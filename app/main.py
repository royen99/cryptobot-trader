import jwt, os, aiohttp, asyncio, secrets, json, time, requests, random
from cryptography.hazmat.primitives import serialization
from collections import deque
import psycopg2 # type: ignore
from psycopg2.extras import Json # type: ignore
from decimal import Decimal
import pandas as pd
import numpy as np
from aiohttp import ClientTimeout

# Network/Retry settings
NET_MAX_RETRIES = 5
NET_BASE_BACKOFF = 0.5   # seconds
NET_TIMEOUT = ClientTimeout(total=12, sock_connect=6, sock_read=6)

DEBUG_MODE = os.getenv("DEBUG_MODE", "False") == "True"  # Set to True for debugging

# Load configuration from config.json
path = os.getenv("CONFIG_PATH", "/config/config.json")
with open(path, "r", encoding="utf-8") as f:
    config = json.load(f)

key_name = config["name"]
key_secret = config["privateKey"]
quote_currency = "USDC"
buy_percentage = config.get("buy_percentage", 10)  # % of available balance to buy
sell_percentage = config.get("sell_percentage", 10)  # % of available balance to sell
stop_loss_percentage = config.get("stop_loss_percentage", -10)  # Stop-loss threshold

request_host = os.getenv("REQUEST_HOST", "api.coinbase.com")

# Database connection parameters (loaded early for coin config fetch)
DB_HOST = config["database"]["host"]
DB_PORT = config["database"]["port"]
DB_NAME = config["database"]["name"]
DB_USER = config["database"]["user"]
DB_PASSWORD = config["database"]["password"]

def get_db_connection():
    """Connect to the PostgreSQL database."""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
    return conn

# Load coin-specific settings from database (now runtime-configurable 🚀)
def load_coins_config_from_db():
    """Fetch coin settings from database and return a dict matching the old JSON structure."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT symbol, enabled, buy_percentage, sell_percentage, rebuy_discount,
                   volatility_window, trend_window, macd_short_window, macd_long_window,
                   macd_signal_window, rsi_period, trail_percent,
                   min_order_buy, min_order_sell, precision_price, precision_amount
            FROM coin_settings
        """)
        rows = cursor.fetchall()
        
        coins = {}
        for row in rows:
            symbol = row[0]
            coins[symbol] = {
                "enabled": row[1],
                "buy_percentage": float(row[2]),
                "sell_percentage": float(row[3]),
                "rebuy_discount": float(row[4]),
                "volatility_window": int(row[5]),
                "trend_window": int(row[6]),
                "macd_short_window": int(row[7]),
                "macd_long_window": int(row[8]),
                "macd_signal_window": int(row[9]),
                "rsi_period": int(row[10]),
                "trail_percent": float(row[11]),
                "min_order_sizes": {
                    "buy": float(row[12]),
                    "sell": float(row[13]),
                },
                "precision": {
                    "price": int(row[14]),
                    "amount": int(row[15]),
                }
            }
        return coins
    except Exception as e:
        print(f"❌ Failed to load coin settings from DB: {e}")
        print("⚠️  Falling back to empty config — check your database!")
        return {}
    finally:
        cursor.close()
        conn.close()

# Load coin config from database
coins_config = load_coins_config_from_db()
crypto_symbols = [symbol for symbol, settings in coins_config.items() if settings.get("enabled", False)]

# Initialize price_history with maxlen equal to the larger of volatility_window and trend_window
if coins_config:
    price_history_maxlen = max(
        max(settings.get("volatility_window", 10) for settings in coins_config.values()),
        max(settings.get("trend_window", 20) for settings in coins_config.values())
    )
else:
    # Fallback if DB is empty (e.g., fresh install before migration)
    price_history_maxlen = 200
    print("⚠️  No coins configured in database. Using default price_history_maxlen=200.")

# Load Telegram settings from config.json
TELEGRAM_CONFIG = config.get("telegram", {})

def send_telegram_notification(message):
    """Send notification to Telegram if enabled in config.json."""
    if not TELEGRAM_CONFIG.get("enabled", False):
        return  # 🔕 Notifications are disabled

    bot_token = TELEGRAM_CONFIG.get("bot_token")
    chat_id = TELEGRAM_CONFIG.get("chat_id")
    
    if not bot_token or not chat_id:
        print("⚠️ Telegram notification skipped: Missing bot token or chat ID in config.json")
        return
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"❌ Telegram Error: {response.text}")
    except Exception as e:
        print(f"❌ Telegram Notification Failed: {e}")

def save_price_history(symbol, price):
    """Save price history to the PostgreSQL database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO price_history (symbol, price)
        VALUES (%s, %s)
        """, (symbol, price))
        conn.commit()
    except Exception as e:
        print(f"Error saving price history to database: {e}")
    finally:
        cursor.close()
        conn.close()

def save_state(symbol, initial_price, total_trades, total_profit):
    """Save the trading state to the PostgreSQL database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO trading_state (symbol, initial_price, total_trades, total_profit)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (symbol) DO UPDATE
        SET initial_price = EXCLUDED.initial_price,
            total_trades = EXCLUDED.total_trades,
            total_profit = EXCLUDED.total_profit
        """, (symbol, initial_price, total_trades, total_profit))
        conn.commit()
    except Exception as e:
        print(f"Error saving state to database: {e}")
    finally:
        cursor.close()
        conn.close()

def load_state(symbol):
    """Load the trading state from the PostgreSQL database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Load trading metrics from trading_state
        cursor.execute("""
        SELECT initial_price, total_trades, total_profit
        FROM trading_state
        WHERE symbol = %s
        """, (symbol,))
        row = cursor.fetchone()

        if row:
            # Convert decimal.Decimal to float if necessary
            initial_price = float(row[0]) if isinstance(row[0], Decimal) else row[0]
            total_trades = int(row[1])
            total_profit = float(row[2]) if isinstance(row[2], Decimal) else row[2]

            # Load price history from price_history table
            cursor.execute("""
            SELECT price
            FROM price_history
            WHERE symbol = %s
            ORDER BY timestamp DESC
            LIMIT %s
            """, (symbol, price_history_maxlen))
            price_history = [float(row[0]) for row in cursor.fetchall()]

            return {
                "price_history": deque(price_history, maxlen=price_history_maxlen),
                "initial_price": initial_price,
                "total_trades": total_trades,
                "total_profit": total_profit,
            }
        return None
    except Exception as e:
        print(f"Error loading state from database: {e}")
        return None
    finally:
        cursor.close()
        conn.close()

# Create a single session to reuse connections (better perf & fewer TLS handshakes)
_aiohttp_session: aiohttp.ClientSession | None = None

async def get_http_session() -> aiohttp.ClientSession:
    global _aiohttp_session
    if _aiohttp_session is None or _aiohttp_session.closed:
        _aiohttp_session = aiohttp.ClientSession(timeout=NET_TIMEOUT)
    return _aiohttp_session

async def jitter_backoff(attempt: int) -> float:
    # exponential backoff with a small random jitter
    return NET_BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 0.2)

def build_jwt(uri):
    """Generate a JWT token for Coinbase API authentication."""
    private_key_bytes = key_secret.encode("utf-8")
    private_key = serialization.load_pem_private_key(private_key_bytes, password=None)

    jwt_payload = {
        "sub": key_name,
        "iss": "cdp",
        "nbf": int(time.time()),
        "exp": int(time.time()) + 120,
        "uri": uri,
    }

    jwt_token = jwt.encode(
        jwt_payload,
        private_key,
        algorithm="ES256",
        headers={"kid": key_name, "nonce": secrets.token_hex()},
    )

    return jwt_token if isinstance(jwt_token, str) else jwt_token.decode("utf-8")

async def api_request(method: str, path: str, body=None):
    """
    Resilient Coinbase API request with retries, backoff, and timeouts.
    Returns parsed JSON or None on persistent failure.
    """
    session = await get_http_session()
    uri = f"{method} {request_host}{path}"
    jwt_token = build_jwt(uri)

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
        "CB-VERSION": "2024-02-05",
    }

    url = f"https://{request_host}{path}"
    last_err = None

    for attempt in range(NET_MAX_RETRIES):
        try:
            async with session.request(method, url, headers=headers, json=body) as resp:
                # Happy path
                if 200 <= resp.status < 300:
                    # some coinbase endpoints return empty body on 204
                    return await (resp.json() if resp.content_type == "application/json" else resp.text())

                # Rate limited -> honor Retry-After header if present
                if resp.status == 429:
                    retry_after = resp.headers.get("Retry-After")
                    wait = float(retry_after) if retry_after else await jitter_backoff(attempt)
                    print(f"⏳ 429 Too Many Requests. Retrying after {wait:.2f}s (attempt {attempt+1}/{NET_MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue

                # Transient server errors -> retry
                if resp.status >= 500:
                    wait = await jitter_backoff(attempt)
                    text = await resp.text()
                    print(f"⚠️ Server error {resp.status}: {text[:200]}... Retrying in {wait:.2f}s (attempt {attempt+1}/{NET_MAX_RETRIES})")
                    await asyncio.sleep(wait)
                    continue

                # Client errors (400-499 excluding 429) -> usually don't retry
                text = await resp.text()
                print(f"❌ API request failed: {resp.status} {text[:300]}")
                return None

        except asyncio.CancelledError:
            # If the process is being shut down, propagate the cancellation
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            last_err = e
            wait = await jitter_backoff(attempt)
            print(f"🌐 Network/timeout error: {type(e).__name__}: {e}. Retrying in {wait:.2f}s (attempt {attempt+1}/{NET_MAX_RETRIES})")
            await asyncio.sleep(wait)
        except Exception as e:
            last_err = e
            print(f"❗ Unexpected error during api_request: {e}")
            break

    print(f"🚫 Giving up after {NET_MAX_RETRIES} attempts. Last error: {last_err}")
    return None

async def get_crypto_price(crypto_symbol: str):
    """Fetch cryptocurrency price from Coinbase. Returns float or None."""
    data = await api_request("GET", f"/api/v3/brokerage/products/{crypto_symbol}-{quote_currency}")
    if not data:
        print(f"⚠️ Failed to fetch {crypto_symbol} price (no data).")
        return None

    # Adapt to actual payload (Coinbase product endpoint often returns nested product info)
    try:
        if "price" in data:
            return float(data["price"])
        if "product" in data and "price" in data["product"]:
            return float(data["product"]["price"])
    except Exception as e:
        print(f"⚠️ Malformed price response for {crypto_symbol}: {e} -> {str(data)[:200]}")

    print(f"⚠️ Price not found in response for {crypto_symbol}.")
    return None

def update_balances(balances):
    """Update the balances table in the database with the provided balances."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for currency, available_balance in balances.items():
            # Insert or update the balance in the database
            cursor.execute("""
            INSERT INTO balances (currency, available_balance)
            VALUES (%s, %s)
            ON CONFLICT (currency) DO UPDATE
            SET available_balance = EXCLUDED.available_balance
            """, (currency, available_balance))
        conn.commit()
    except Exception as e:
        print(f"Error updating balances: {e}")
    finally:
        cursor.close()
        conn.close()

async def get_balances():
    """Fetch balances from Coinbase and return them as a dictionary."""
    path = "/api/v3/brokerage/accounts"
    data = await api_request("GET", path)  # Await the API request
    
    balances = {}
    if "accounts" in data:
        for account in data["accounts"]:
            currency = account["currency"]
            available_balance = float(account["available_balance"]["value"])
            balances[currency] = available_balance
    
    return balances

async def place_order(crypto_symbol, side, amount, current_price):
    """Place a buy/sell order for the specified cryptocurrency asynchronously."""
    path = "/api/v3/brokerage/orders"
    
    order_data = {
        "client_order_id": secrets.token_hex(16),
        "product_id": f"{crypto_symbol}-{quote_currency}",
        "side": side,
        "order_configuration": {
            "market_market_ioc": {}
        }
    }
    
    min_order_sizes = coins_config[crypto_symbol]["min_order_sizes"]
    
    if side == "BUY":
        # Get precision settings for this coin
        amount_precision = coins_config[crypto_symbol].get("precision", {}).get("amount", 6)

        # Calculate total cost in USDC **before** rounding amount
        quote_cost = round(current_price * amount, 2)

        # Ensure buy order is above minimum required buy amount
        if quote_cost < min_order_sizes["buy"]:
            print(f"🚫  - Buy order too small: ${quote_cost} (minimum: ${min_order_sizes['buy']})")
            return False
        
        # Round amount according to precision
        rounded_amount = round(amount, amount_precision)

        # Assign quote_size (amount in USDC) for API order
        order_data["order_configuration"]["market_market_ioc"]["quote_size"] = str(quote_cost)

    else:  # SELL
        # Get required precision from config
        precision = coins_config[crypto_symbol]["precision"]["amount"]

        # 🔧 Round to correct precision dynamically
        rounded_amount = round(amount, precision)

        # 🚨 Ensure sell amount meets minimum order size
        if rounded_amount < min_order_sizes["sell"]:
            print(f"🚫  - Sell order too small: {rounded_amount:.{precision}f} {crypto_symbol} (minimum: {min_order_sizes['sell']:.{precision}f} {crypto_symbol})")
            return False

        # 🔄 Ensure the API receives the correctly formatted amount
        order_data["order_configuration"]["market_market_ioc"]["base_size"] = str(f"{rounded_amount:.{precision}f}")

        print(f"🛠️  - Adjusted Sell Amount for {crypto_symbol}: {rounded_amount:.{precision}f} (Precision: {precision})")
    
    # Log the order details
    print(f"🛠️  - Placing {side} order for {crypto_symbol}: Amount = {rounded_amount}, Price = {await get_crypto_price(crypto_symbol)}")

    response = await api_request("POST", path, order_data)

    if DEBUG_MODE:
        print(f"🔄 Raw Response: {response}")  # Only log raw response in debug mode

    # Handle the response
    if response.get("success", False):
        order_id = response["success_response"]["order_id"]
        print(f"✅  - {side.upper()} Order Placed for {crypto_symbol}: Order ID = {order_id}")
        
        # Log the trade in the database
        current_price = await get_crypto_price(crypto_symbol)
        if current_price:
            await log_trade(crypto_symbol, side, rounded_amount, current_price)

        return True
    else:
        print(f"❌  - Order Failed for {crypto_symbol}: {response.get('error', 'Unknown error')}")
        print(f"🔄  - Raw Response: {response}")
        message = f"⚠️ Order Failed for {crypto_symbol}"
        send_telegram_notification(message)
        return False

async def log_trade(symbol, side, amount, price):
    """Log a trade in the trades table."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
        INSERT INTO trades (symbol, side, amount, price)
        VALUES (%s, %s, %s, %s)
        """, (symbol, side, amount, price))
        conn.commit()
    except Exception as e:
        print(f"Error logging trade: {e}")
    finally:
        cursor.close()
        conn.close()

def calculate_volatility(price_history, volatility_window):
    """Calculate volatility as the standard deviation of price changes over a specific window."""
    if len(price_history) < volatility_window:
        return 0.0
    recent_prices = list(price_history)[-volatility_window:]
    price_changes = np.diff(recent_prices) / recent_prices[:-1]  # Percentage changes
    return np.std(price_changes)  # Standard deviation of returns

def calculate_moving_average(price_history, trend_window):
    if len(price_history) < trend_window:
        return None
    # Use deque for O(1) append/pop (better for streaming data)
    window_prices = price_history[-trend_window:]
    return sum(window_prices) / trend_window

def calculate_ema(prices, period, return_all=False):
    """Calculate the Exponential Moving Average (EMA) for a given period."""
    if len(prices) < period:
        return None if not return_all else []

    multiplier = 2 / (period + 1)
    ema_values = [sum(prices[:period]) / period]  # Start with SMA

    for price in prices[period:]:
        ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])

    return ema_values if return_all else ema_values[-1]

def calculate_macd(prices, symbol, short_window=12, long_window=26, signal_window=9):
    """Calculate MACD, Signal Line, and Histogram."""
    if len(prices) < long_window + signal_window:
        print(f"⚠️  - Not enough data to calculate MACD for {symbol}. Required: {long_window + signal_window}, Available: {len(prices)}")
        return None, None, None

    # Compute EMA for the full dataset
    short_ema = calculate_ema(prices, short_window, return_all=True)
    long_ema = calculate_ema(prices, long_window, return_all=True)

    # Calculate MACD Line (difference between short and long EMA)
    macd_line_values = [s - l for s, l in zip(short_ema, long_ema)]

    # Calculate Signal Line (EMA of MACD Line)
    signal_line_values = calculate_ema(macd_line_values, signal_window, return_all=True)

    # Calculate MACD Histogram
    macd_histogram_values = [m - s for m, s in zip(macd_line_values[-len(signal_line_values):], signal_line_values)]

    return macd_line_values[-1], signal_line_values[-1], macd_histogram_values[-1]

def calculate_rsi(prices, symbol, period=14):
    """Calculate the Relative Strength Index (RSI)."""
    if len(prices) < period + 1:
        print(f"⚠️  - Not enough data to calculate RSI for {symbol}. Required: {period + 1}, Available: {len(prices)}")
        return None

    # Calculate gains and losses
    changes = np.diff(prices)
    gains = np.maximum(changes, 0)
    losses = np.maximum(-changes, 0)

    # Calculate average gains and losses
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    # EMA smoothing for RSI
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_long_term_ma(price_history, period=200):
    """Calculate the long-term moving average."""
    if len(price_history) < period:
        return None
    return sum(price_history[-period:]) / period

def save_weighted_avg_buy_price(symbol, avg_price):
    """Store the latest weighted average buy price for a given symbol in the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    if avg_price is not None:
        cursor.execute(
            """
            INSERT INTO trading_state (symbol, initial_price, total_trades, total_profit)
            VALUES (%s, %s, 0, 0)
            ON CONFLICT (symbol) DO UPDATE
            SET initial_price = EXCLUDED.initial_price
            """,
            (symbol, avg_price)
        )

        print(f"💾  - {symbol} Weighted Average Buy Price Updated: {avg_price:.6f} USDC")

    conn.commit()
    cursor.close()
    conn.close()

def get_weighted_avg_buy_price(symbol):
    """Fetch the weighted average buy price since the last sell from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # ✅ Step 1: Get the most recent SELL trade timestamp
    cursor.execute(
        """
        SELECT timestamp FROM trades 
        WHERE symbol = %s AND side = 'SELL' 
        ORDER BY timestamp DESC 
        LIMIT 1
        """,
        (symbol,)
    )
    last_sell = cursor.fetchone()
    last_sell_time = last_sell[0] if last_sell else None

    # ✅ Step 2: Fetch all BUY trades after the last sell (or all if no sells exist)
    if last_sell_time:
        cursor.execute(
            """
            SELECT amount, price FROM trades 
            WHERE symbol = %s AND side = 'BUY' 
            AND timestamp > %s
            """,
            (symbol, last_sell_time)
        )
    else:
        # If no previous sell exists, get all buys
        cursor.execute(
            "SELECT amount, price FROM trades WHERE symbol = %s AND side = 'BUY'",
            (symbol,)
        )

    buy_trades = cursor.fetchall()
    cursor.close()
    conn.close()

    if not buy_trades:
        if DEBUG_MODE:
            print(f"⚠️  - No buy trades found for {symbol} after last sell.")

        # If no buy trades exist, return None
        return None

    # ✅ Step 3: Calculate the **correct** weighted average price
    total_amount = sum(trade[0] for trade in buy_trades)  # Sum of all bought amounts
    if total_amount == 0:
        print(f"🔥  - Total amount for {symbol} is 0. Returning None.")
        return None  # Prevent division by zero

    weighted_avg_price = sum(trade[0] * trade[1] for trade in buy_trades) / total_amount

    # print(f"📊 DEBUG - {symbol}: Found {len(buy_trades)} BUY trades after last sell. Calculated Avg Price: {weighted_avg_price:.6f}")
    
    return weighted_avg_price

def calculate_stochastic_rsi(rsi_values, period=14, k_period=3, d_period=3):
    if len(rsi_values) < period + d_period:
        return None, None

    rsi_series = pd.Series(rsi_values)
    stoch_rsi = (rsi_series - rsi_series.rolling(window=period).min()) / (
        rsi_series.rolling(window=period).max() - rsi_series.rolling(window=period).min()
    )

    k_line = stoch_rsi.rolling(window=k_period).mean()
    d_line = k_line.rolling(window=d_period).mean()

    return k_line.iloc[-1], d_line.iloc[-1]

def calculate_bollinger_bands(prices, period=20, num_std_dev=2):
    price_series = pd.Series(prices)
    middle_band = price_series.rolling(window=period).mean()
    std_dev = price_series.rolling(window=period).std()
    upper_band = middle_band + (num_std_dev * std_dev)
    lower_band = middle_band - (num_std_dev * std_dev)
    return middle_band.iloc[-1], upper_band.iloc[-1], lower_band.iloc[-1]

async def process_manual_commands():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, symbol, action 
        FROM manual_commands 
        WHERE executed = FALSE
    """)
    commands = cursor.fetchall()

    for cmd in commands:
        cmd_id, symbol, action = cmd
        action = action.upper()

        if symbol in crypto_data:
            crypto_data[symbol]["manual_cmd"] = action
            print(f"📥 Manual command received: {action} for {symbol}")
        else:
            print(f"⚠️ Unknown symbol in manual command: {symbol}")

        # Mark as executed
        cursor.execute("UPDATE manual_commands SET executed = TRUE WHERE id = %s", (cmd_id,))
        conn.commit()

    cursor.close()
    conn.close()

def _fmt(v, nd=6):
    try:
        return f"{v:.{nd}f}"
    except Exception:
        return str(v)

def debug_buy_blockers(symbol, reasons):
    """reasons = list of dicts: {'name': str, 'ok': bool, 'detail': str}"""
    blockers = [r for r in reasons if not r['ok']]
    if not blockers:
        return
    print(f"🧰 BUY blocked for {symbol}. Unmet conditions:")
    for r in blockers:
        print(f"   - {r['name']}: {r['detail']}")

# Initialize somee global variables
crypto_data = {}
actual_buy_price = {}

# Global variable to track MACD confirmation
macd_confirmation = {symbol: {"buy": 0, "sell": 0} for symbol in crypto_symbols}

async def trading_bot():
    global crypto_data, macd_confirmation

    # Initialize initial prices for all cryptocurrencies
    for symbol in crypto_symbols:
        state = load_state(symbol)
        if state:
            crypto_data[symbol] = state
        else:
            initial_price = await get_crypto_price(symbol)
            if not initial_price:
                print(f"🚨 Failed to fetch initial {symbol} price. Skipping {symbol}.")
                continue
            crypto_data[symbol] = {
                "price_history": deque([initial_price], maxlen=price_history_maxlen),
                "initial_price": initial_price,
                "total_trades": 0,
                "total_profit": 0.0,
            }
            save_state(symbol, initial_price, 0, 0.0)
            print(f"🔍 Monitoring {symbol}... Initial Price: ${initial_price}, Price History: {crypto_data[symbol]['price_history']}")

    while True:
        await asyncio.sleep(25)  # Wait before checking prices again

        # Fetch balances
        balances = await get_balances()

        # Log balances
        print("💰 Available Balances:")
        for currency, balance in balances.items():
            print(f"  - {currency}: {balance}")

        # Update balances in the database
        update_balances(balances)

        # Fetch prices for all cryptocurrencies concurrently
        price_tasks = [get_crypto_price(symbol) for symbol in crypto_symbols]
        prices = await asyncio.gather(*price_tasks)

        # 🧠 Refresh manual commands for this cycle
        await process_manual_commands()

        for symbol, current_price in zip(crypto_symbols, prices):
            price_precision = coins_config[symbol]["precision"]["price"]  # Get the decimal places from config

            if not current_price:
                print(f"🚨 {symbol}: No price data. Skipping.")
                continue
            if symbol not in crypto_data:
                print(f"🚨 {symbol}: Not in crypto_data. Skipping.")
                continue
            if not crypto_data[symbol]["price_history"]:
                print(f"🚨 {symbol}: Empty price_history. Skipping.")
                continue
            if current_price == crypto_data[symbol]["price_history"][-1]:
                print(f"🚨 {symbol}: Price unchanged ({current_price:.{price_precision}f} == {crypto_data[symbol]['price_history'][-1]:.{price_precision}f}). Skipping.")
                continue

            # Save price history
            save_price_history(symbol, current_price)

            # Update price history in memory
            crypto_data[symbol]["price_history"].append(current_price)
            price_history = list(crypto_data[symbol]["price_history"])
            previous_price = crypto_data[symbol].get("previous_price")
            
            # Check for a rising streak (if price is rising and continues to rise)
            if previous_price is not None:
                if current_price > previous_price:
                    crypto_data[symbol]["rising_streak"] = crypto_data[symbol].get("rising_streak", 0) + 1
                    print(f"📈 {symbol} Rising Streak: {crypto_data[symbol]['rising_streak']}")
                else:
                    crypto_data[symbol]["rising_streak"] = 0

            # Check for a falling streak (if price is falling and continues to fall)
            if previous_price is not None:
                if current_price < previous_price:
                    crypto_data[symbol]["falling_streak"] = crypto_data[symbol].get("falling_streak", 0) + 1
                    print(f"📉 {symbol} Falling Streak: {crypto_data[symbol]['falling_streak']}")
                else:
                    crypto_data[symbol]["falling_streak"] = 0
        
            # Get coin-specific settings
            coin_settings = coins_config[symbol]
            buy_threshold = coin_settings["buy_percentage"]
            sell_threshold = coin_settings["sell_percentage"]
            rebuy_discount = coin_settings["rebuy_discount"]
            volatility_window = coin_settings["volatility_window"]
            trend_window = coin_settings["trend_window"]
            macd_short_window = coin_settings["macd_short_window"]
            macd_long_window = coin_settings["macd_long_window"]
            macd_signal_window = coin_settings["macd_signal_window"]
            rsi_period = coin_settings["rsi_period"]
            trail_percent = coin_settings.get("trail_percent", 0.5)  # Default to 0.5% if not specified

            if balances.get(symbol, 0.0) > 0 and current_price > crypto_data[symbol].get("peak_price", 0):
                crypto_data[symbol]["peak_price"] = current_price

            peak_price = crypto_data[symbol].get("peak_price")
            trail_stop_price = peak_price * (1 - trail_percent / 100) if peak_price else None

            # Ensure we have enough data for indicators
            if len(price_history) < max(macd_long_window + macd_signal_window, rsi_period + 1):
                print(f"⚠️ {symbol}: Not enough data for indicators. Required: {max(macd_long_window + macd_signal_window, rsi_period + 1)}, Available: {len(price_history)}")
                continue

            long_term_ma = calculate_long_term_ma(price_history, period=200)
            if long_term_ma is None:
                print(f"⚠️ {symbol}: Not enough data for long-term MA. Skipping.")
                continue

            price_change = ((current_price - crypto_data[symbol]["initial_price"]) / crypto_data[symbol]["initial_price"]) * 100

            peak_display = f"${peak_price:.{price_precision}f}" if peak_price else "N/A"
            trail_display = f"${trail_stop_price:.{price_precision}f}" if trail_stop_price else "N/A"
            print(f"🚀 {symbol} - Current Price: ${current_price:.{price_precision}f} ({price_change:.2f}%), Peak Price: {peak_display}, Trailing Stop Price: {trail_display}")

            # Calculate volatility and moving average
            volatility = calculate_volatility(price_history, volatility_window)
            volatility_factor = min(1.5, max(0.5, 1 + abs(volatility)))  # Cap extreme changes
            moving_avg = calculate_moving_average(price_history, trend_window)

            # Calculate indicators
            macd_line, signal_line, macd_histogram = calculate_macd(
                price_history, symbol, macd_short_window, macd_long_window, macd_signal_window
            )
            rsi = calculate_rsi(price_history, symbol)

            # Calculate Stochastic RSI
            crypto_data[symbol].setdefault("rsi_history", [])
            crypto_data[symbol]["rsi_history"].append(rsi)
            if len(crypto_data[symbol]["rsi_history"]) > 50:
                crypto_data[symbol]["rsi_history"].pop(0)

            k, d = calculate_stochastic_rsi(crypto_data[symbol]["rsi_history"])
            crypto_data[symbol]["stoch_k"] = k
            crypto_data[symbol]["stoch_d"] = d

            if k is not None and d is not None and (k < 0.2 and k > d):
                print(f"🔥 {symbol} Stochastic RSI Buy Signal: K = {k:.2f}, D = {d:.2f}")

            if k is not None and d is not None and (k > 0.8 and k < d):
                print(f"🔥 {symbol} Stochastic RSI Sell Signal: K = {k:.2f}, D = {d:.2f}")

            bollinger_mid, bollinger_upper, bollinger_lower = calculate_bollinger_bands(price_history)
            crypto_data[symbol]['bollinger'] = {
                'mid': bollinger_mid,
                'upper': bollinger_upper,
                'lower': bollinger_lower
            }

            bollinger_buy_signal = current_price < bollinger_lower if bollinger_lower else False
            bollinger_sell_signal = current_price > bollinger_upper if bollinger_upper else False

            if DEBUG_MODE:
                # Log indicator values
                print(f"📊 {symbol} Indicators - Volatility: {volatility:.4f}, Moving Avg: {moving_avg:.4f}, MACD: {macd_line:.4f}, Signal: {signal_line:.4f}, RSI: {rsi:.2f}")

            # Adjust thresholds based on volatility
            dynamic_buy_threshold = buy_threshold * volatility_factor
            dynamic_sell_threshold = sell_threshold * volatility_factor

            # Get average buy price
            actual_buy_price = get_weighted_avg_buy_price(symbol)

            # Calculate expected buy/sell prices
            if actual_buy_price is not None:
                expected_buy_price = actual_buy_price
                expected_sell_price = actual_buy_price * (1 + dynamic_sell_threshold / 100)
            else:
                expected_buy_price = crypto_data[symbol]["initial_price"] * (1 + dynamic_buy_threshold / 100)
                expected_sell_price = crypto_data[symbol]["initial_price"] * (1 + dynamic_sell_threshold / 100)

            if DEBUG_MODE:
                # Log expected prices
                print(f"📊  - Expected Prices for {symbol}: Buy at: ${expected_buy_price:.{price_precision}f} ({dynamic_buy_threshold:.2f}%) / Sell at: ${expected_sell_price:.{price_precision}f} ({dynamic_sell_threshold:.2f}%) | MA: {moving_avg:.{price_precision}f}")

                # Log Bollinger Bands
                print(f"🔔  - Bollinger Bands for {symbol}: Mid: ${bollinger_mid:.{price_precision}f}, Upper: ${bollinger_upper:.{price_precision}f}, Lower: ${bollinger_lower:.{price_precision}f}")

            # Check if the price is close to the moving average
            if (moving_avg and abs(current_price - moving_avg) < (0.1 * moving_avg)) or crypto_data[symbol].get("manual_cmd") is not None:

                # MACD Buy Signal: MACD line crosses above Signal line
                macd_buy_signal = macd_line is not None and signal_line is not None and macd_line > signal_line
                
                # RSI Buy Signal: RSI is below 35 (oversold)
                rsi_buy_signal = rsi is not None and rsi < 35
                
                # MACD Sell Signal: MACD line crosses below Signal line
                macd_sell_signal = macd_line is not None and signal_line is not None and macd_line < signal_line
                
                # RSI Sell Signal: RSI is above 70 (overbought)
                rsi_sell_signal = rsi is not None and rsi > 65

                # MACD Confirmation Rule with decay instead of full reset
                if macd_buy_signal:
                    macd_confirmation[symbol]["buy"] += 1
                    macd_confirmation[symbol]["sell"] = max(0, macd_confirmation[symbol]["sell"] - 1)
                elif macd_sell_signal:
                    macd_confirmation[symbol]["sell"] += 1
                    macd_confirmation[symbol]["buy"] = max(0, macd_confirmation[symbol]["buy"] - 1)
                else:
                    macd_confirmation[symbol]["buy"] = max(0, macd_confirmation[symbol]["buy"] - 1)
                    macd_confirmation[symbol]["sell"] = max(0, macd_confirmation[symbol]["sell"] - 1)

                if DEBUG_MODE:
                    # Log trading signals if debug is set
                    print(f"📊 {symbol} Trading Signals - MACD Buy: {macd_buy_signal}, RSI Buy: {rsi_buy_signal}, MACD Sell: {macd_sell_signal}, RSI Sell: {rsi_sell_signal}")
                    print(f"📊 {symbol} MACD Confirmation - Buy: {macd_confirmation[symbol]['buy']}, Sell: {macd_confirmation[symbol]['sell']}")

                # Check how long since the last buy
                time_since_last_buy = time.time() - crypto_data[symbol].get("last_buy_time", 0)

                # 🔥 Gradual Adjustments: Move `initial_price` 10% closer to `long_term_ma` during a sustained >5% uptrend
                if (
                    time_since_last_buy > 900
                    and price_change >= dynamic_sell_threshold
                    and current_price > crypto_data[symbol]["initial_price"] * 1.05
                    and current_price > long_term_ma  # Confirm Uptrend
                    ):
                    new_initial_price = (
                        0.9 * crypto_data[symbol]["initial_price"] + 0.1 * long_term_ma
                    )
                    print(f"📈  - {symbol} Adjusting Initial Price Upwards: {crypto_data[symbol]['initial_price']:.{price_precision}f} → {new_initial_price:.{price_precision}f}")
                    crypto_data[symbol]["initial_price"] = new_initial_price

                    # Persist only the new initial price and leave other values unchanged, this has save_state(symbol, initial_price, total_trades, total_profit)
                    save_state(symbol, new_initial_price, crypto_data[symbol]["total_trades"], crypto_data[symbol]["total_profit"])    

                # 🔽 Adjust Initial Price Downwards in a Sustained Downtrend (If Holdings < 1 USDC)
                elif (
                    time_since_last_buy > 3600 and  # Time check
                    balances.get(symbol, 0) * current_price < 1 and  # Holdings worth less than $1 USDC
                    current_price < crypto_data[symbol]["initial_price"] * 0.95 # Prevent premature resets
                ):
                    new_initial_price = (0.9 * crypto_data[symbol]["initial_price"] + 0.1 * current_price)  # Move closer to the current price
                    print(f"📉   - {symbol} Adjusting Initial Price Downwards: {crypto_data[symbol]['initial_price']:.{price_precision}f} → {new_initial_price:.{price_precision}f}")
                    crypto_data[symbol]["initial_price"] = new_initial_price

                    # Persist only the new initial price and leave other values unchanged
                    save_state(symbol, new_initial_price, crypto_data[symbol]["total_trades"], crypto_data[symbol]["total_profit"])

                if bollinger_buy_signal:
                    print(f"💘 {symbol}: Price is below Bollinger Lower Band (${bollinger_lower:.2f}) — buy signal!")

                if bollinger_sell_signal:
                    print(f"💔 {symbol}: Price is above Bollinger Upper Band (${bollinger_upper:.2f}) — sell signal!")

                if actual_buy_price is not None and current_price > actual_buy_price * (1 + (dynamic_sell_threshold / 100)):
                    print(f"💵 {symbol}: Price is above expected sell price (${expected_sell_price:.{price_precision}f}) — sell signal 🚨 !!!")

                price_slope = current_price - price_history[-3]

                # Execute buy order if signals are confirmed
                cond_bollinger_primary = (bollinger_lower is None or current_price < bollinger_lower)

                cond_stoch_part = (k is None or d is None or (k < 0.2 and k > d))
                cond_bollinger_stoch = ((bollinger_mid is None or current_price < bollinger_mid) and cond_stoch_part)

                cond_entry_band = (cond_bollinger_primary or cond_bollinger_stoch)

                cond_price_thresh = (
                    price_change <= dynamic_buy_threshold
                    and actual_buy_price is None
                )

                cond_rebuy_discount = (
                    actual_buy_price is not None
                    and current_price < actual_buy_price * (1 - rebuy_discount / 100.0)
                )

                cond_trend = (current_price < long_term_ma)
                cond_cooldown = (time_since_last_buy > 120)
                cond_streak = (crypto_data[symbol].get("rising_streak", 0) > 1)
                cond_balance = (balances[quote_currency] > 0)
                cond_manual = (crypto_data[symbol].get("manual_cmd") == "BUY")

                # Full BUY condition
                auto_buy_condition = (
                    cond_entry_band
                    and (cond_price_thresh or cond_rebuy_discount)
                    and cond_trend
                    and cond_cooldown
                    and cond_streak
                    and cond_balance
                )
                buy_condition = (auto_buy_condition or cond_manual)

                # If buy not triggered, explain what's missing (when in DEBUG)
                if DEBUG_MODE and not buy_condition and not cond_manual:
                    reasons = [
                        {
                            "name": "Entry band",
                            "ok": cond_entry_band,
                            "detail": (
                                f"need (price<{_fmt(bollinger_lower)} OR (price<{_fmt(bollinger_mid)} "
                                f"AND StochK/D bullish<0.2)); price={_fmt(current_price)}; "
                                f"K={_fmt(k) if k is not None else 'None'}, D={_fmt(d) if d is not None else 'None'}"
                            )
                        },
                        {
                            "name": "Price threshold OR Rebuy discount",
                            "ok": (cond_price_thresh or cond_rebuy_discount),
                            "detail": (
                                f"price_change={price_change:.2f}% vs dyn_buy={dynamic_buy_threshold:.2f}%  |  "
                                f"rebuy: actual_buy={_fmt(actual_buy_price)} -> target<{(1 - rebuy_discount/100):.3f}*buy"
                            )
                        },
                        {
                            "name": "Trend (below long-term MA)",
                            "ok": cond_trend,
                            "detail": f"current={_fmt(current_price)} < long_MA={_fmt(long_term_ma)}"
                        },
                        {
                            "name": "Cooldown",
                            "ok": cond_cooldown,
                            "detail": f"since_last_buy={int(time_since_last_buy)}s > 120s"
                        },
                        {
                            "name": "Rising streak > 1",
                            "ok": cond_streak,
                            "detail": f"rising_streak={crypto_data[symbol].get('rising_streak', 0)} > 1"
                        },
                        {
                            "name": "USDC balance",
                            "ok": cond_balance,
                            "detail": f"{quote_currency}={_fmt(balances.get(quote_currency, 0), 2)} > 0"
                        },
                    ]
                    debug_buy_blockers(symbol, reasons)

                # Execute buy if condition met
                if buy_condition:
                    quote_cost = round((buy_percentage / 100) * balances[quote_currency], 2)  # USDC
                    if quote_cost < coins_config[symbol]["min_order_sizes"]["buy"]:
                        print(f"🚫  - Buy order too small: ${quote_cost:.2f} (minimum: ${coins_config[symbol]['min_order_sizes']['buy']})")
                        crypto_data[symbol]["manual_cmd"] = None
                    else:
                        buy_amount = quote_cost / current_price
                        print(f"💰 Buying {buy_amount:.6f} {symbol} (${quote_cost:.2f} USDC)!")
                        if await place_order(symbol, "BUY", buy_amount, current_price):
                            crypto_data[symbol]["manual_cmd"] = None
                            crypto_data[symbol]["total_trades"] += 1
                            crypto_data[symbol]["last_buy_time"] = time.time()

                            updated_avg_price = get_weighted_avg_buy_price(symbol)
                            save_weighted_avg_buy_price(symbol, updated_avg_price)

                            message = f"✅ *BOUGHT {buy_amount:.4f} {symbol}* at *${current_price:.{price_precision}f}* USDC"
                            send_telegram_notification(message)

                            crypto_data[symbol]["peak_price"] = current_price

                elif (
                    # Execute sell order if sell signals are confirmed and dynamic_sell_threshold was reached
                    ((
                        (
                            macd_sell_signal
                            and macd_confirmation[symbol]["sell"] >= 3  # ✅ At least 3 positives signals
                            and (k is None or d is None or (k > 0.8 and k < d))  # ✅ Overbought and bearish cross
                            and (bollinger_upper is None or current_price > bollinger_mid)  # ✅ Bollinger confirms price is still warm
                        )
                        or
                        (
                            (bollinger_upper is not None and current_price > bollinger_upper)  # ✅ Bollinger confirms price is hot
                        )
                    )
                    and actual_buy_price is not None  # ✅ Ensure actual_buy_price is valid before using it
                    and current_price > actual_buy_price * (1 + (dynamic_sell_threshold / 100))  # ✅ Profit percentage wanted based on sell threshold
                    and crypto_data[symbol].get("falling_streak", 0) > 1  # ✅ Ensure we’re not in a rising streak
                    and balances[symbol] > 0  # ✅ Ensure we have balance
                    )
                    or crypto_data[symbol].get("manual_cmd") == "SELL"  # Manual sell command
                ):

                    sell_amount = (sell_percentage / 100) * balances[symbol]

                    # Get required precision from config
                    precision = coins_config[symbol]["precision"]["amount"]

                    # 🔧 Round down sell amount to match precision
                    sell_amount = round(sell_amount, precision)

                    # 🚨 Ensure we don’t try selling more than available balance
                    safe_margin = 10 ** -precision  # Smallest allowed unit (e.g., 0.000001 for 6 decimals)
                    sell_amount = min(sell_amount, balances[symbol] - safe_margin)  # Avoid over-selling

                    if sell_amount > 0:
                        print(f"💵  - Selling {sell_amount:.{precision}f} {symbol} at {current_price:.2f}!")

                        # 🔥 Get actual weighted buy price from DB just before selling
                        actual_buy_price = get_weighted_avg_buy_price(symbol)

                        if await place_order(symbol, "SELL", sell_amount, current_price):
                            crypto_data[symbol]["total_trades"] += 1

                            if actual_buy_price is None:
                                print(f"❌  - ERROR: get_weighted_avg_buy_price({symbol}) returned None! Check DB query!")

                            else:
                                print(f"✅  - SUCCESS: Weighted Avg Buy Price for {symbol} = {actual_buy_price:.{price_precision}f}")

                            if actual_buy_price:
                                crypto_data[symbol]["total_profit"] += (current_price - actual_buy_price) * sell_amount
                                sell_profit = (current_price - actual_buy_price) * sell_amount
                                print(f"💰  - {symbol} Profit Calculated: (Sell: {current_price:.{price_precision}f} - Buy: {actual_buy_price:.{price_precision}f}) * {sell_amount:.4f} = {crypto_data[symbol]['total_profit']:.2f} USDC")
                            else:
                                print(f"⚠️  - No buy data found for {symbol}. Profit calculation skipped.")

                            # 🔄 Reset initial price to long-term MA after sell to allow re-entry
                            crypto_data[symbol]["initial_price"] = long_term_ma
                            print(f"🔄  - {symbol} Initial Price Reset to Long-Term MA: {long_term_ma:.{price_precision}f}")

                            # 🔥 Save Weighted Avg Buy Price After Sell
                            save_weighted_avg_buy_price(symbol, None)  # Reset buy price after sell

                            # Send Telegram notification incl. total profit from this trade and total sell price in USDC
                            message = f"🚀 *SOLD {sell_amount:.4f} {symbol}* at *${current_price:.{price_precision}f}* USDC (Total USDC: {sell_amount * current_price:.{price_precision}f}), *Total Profit: {sell_profit:.2f}* USDC"
                            send_telegram_notification(message)
                            crypto_data[symbol]["manual_cmd"] = None

                        else:
                            print(f"🚫  - Sell order failed for {symbol}!")

            else:
                deviation = abs(current_price - moving_avg)  # Calculate deviation
                deviation_percentage = (deviation / moving_avg) * 100  # Convert to percentage
                message = f"🚀 Large deviation for {symbol} - {deviation_percentage:.2f}%, Current Price: {current_price:.{price_precision}f} USDC"
                print(f"🔥  - {symbol} Skipping trade: Price deviation too high!")
                print(f"📊  - Moving Average: {moving_avg:.{price_precision}f}, Current Price: {current_price:.{price_precision}f}")
                print(f"📉  - Deviation: {deviation:.2f} ({deviation_percentage:.2f}%)")

            print(f"📊  - {symbol} Avg buy price: {actual_buy_price} | Performance - Total Trades: {crypto_data[symbol]['total_trades']} | Total Profit: ${crypto_data[symbol]['total_profit']:.2f}")
            crypto_data[symbol]["manual_cmd"] = None  # Set to None at the start of each cycle

            # Save state after each coin's update
            save_state(symbol, crypto_data[symbol]["initial_price"], crypto_data[symbol]["total_trades"], crypto_data[symbol]["total_profit"])

            crypto_data[symbol]["previous_price"] = current_price

if __name__ == "__main__":
    asyncio.run(trading_bot())
