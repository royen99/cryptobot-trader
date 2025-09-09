
import os, json, time, asyncio, secrets, requests
from decimal import Decimal
from collections import deque

import psycopg2  # type: ignore
from psycopg2.extras import Json  # type: ignore

import numpy as np
import pandas as pd

from app.exchanges import create_exchange
from app.exchanges.base import Exchange

# ----------------- Load configuration -----------------
path = os.getenv("CONFIG_PATH", "/config/config.json")
with open(path, "r", encoding="utf-8") as f:
    config = json.load(f)

DEBUG_MODE = os.getenv("DEBUG_MODE", "False") == "True"

# DB config
DB_HOST = config["database"]["host"]
DB_PORT = config["database"]["port"]
DB_NAME = config["database"]["name"]
DB_USER = config["database"]["user"]
DB_PASSWORD = config["database"]["password"]

# Telegram config
TELEGRAM_CONFIG = config.get("telegram", {})

# Coins config
coins_config = config.get("coins", {})
crypto_symbols = [symbol for symbol, settings in coins_config.items() if settings.get("enabled", False)]

# price_history maxlen
price_history_maxlen = max(
    max(settings.get("volatility_window", 10) for settings in coins_config.values()),
    max(settings.get("trend_window", 20) for settings in coins_config.values())
)

# --- Exchange factory ---
exchange_cfg = config.get("exchange", {})
exchange: Exchange = create_exchange(exchange_cfg)
quote_currency = exchange.quote_currency

# --- Global sizing (order size) ---
SIZE_BUY_PCT  = float(abs(config.get("buy_percentage", 20)))   # e.g. 20 => buy 20% of quote balance
SIZE_SELL_PCT = float(abs(config.get("sell_percentage", 100))) # e.g. 100 => sell 100% of base balance

# ----------------- DB helpers -----------------
def get_db_connection():
    conn = psycopg2.connect(
        host=DB_HOST, port=DB_PORT, database=DB_NAME, user=DB_USER, password=DB_PASSWORD
    )
    return conn

def update_balances_ex(balances: dict[str, float], exchange_name: str) -> None:
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        for currency, available_balance in balances.items():
            cur.execute("""
                INSERT INTO balances (exchange, currency, available_balance)
                VALUES (%s, %s, %s)
                ON CONFLICT (exchange, currency) DO UPDATE
                SET available_balance = EXCLUDED.available_balance
            """, (exchange_name, currency, available_balance))
        conn.commit()
    except Exception as e:
        print(f"Error updating balances: {e}")
    finally:
        cur.close(); conn.close()

def save_price_history(symbol, price):
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO price_history (symbol, price) VALUES (%s, %s)", (symbol, price))
        conn.commit()
    except Exception as e:
        print(f"Error saving price history: {e}")
    finally:
        cur.close(); conn.close()

def save_state(symbol, initial_price, total_trades, total_profit):
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO trading_state (symbol, initial_price, total_trades, total_profit)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (symbol) DO UPDATE
            SET initial_price = EXCLUDED.initial_price,
                total_trades = EXCLUDED.total_trades,
                total_profit = EXCLUDED.total_profit
            """,
            (symbol, initial_price, total_trades, total_profit),
        )
        conn.commit()
    except Exception as e:
        print(f"Error saving state: {e}")
    finally:
        cur.close(); conn.close()

def load_state(symbol):
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT initial_price, total_trades, total_profit
            FROM trading_state WHERE symbol=%s
            """,
            (symbol,),
        )
        row = cur.fetchone()
        if row:
            initial_price = float(row[0]) if isinstance(row[0], Decimal) else row[0]
            total_trades = int(row[1])
            total_profit = float(row[2]) if isinstance(row[2], Decimal) else row[2]

            cur.execute(
                """
                SELECT price FROM price_history
                WHERE symbol=%s ORDER BY timestamp DESC
                LIMIT %s
                """,
                (symbol, price_history_maxlen),
            )
            ph = [float(r[0]) for r in cur.fetchall()]
            return {
                "price_history": deque(ph, maxlen=price_history_maxlen),
                "initial_price": initial_price,
                "total_trades": total_trades,
                "total_profit": total_profit,
            }
        return None
    except Exception as e:
        print(f"Error loading state: {e}")
        return None
    finally:
        cur.close(); conn.close()

def send_telegram_notification(message: str):
    if not TELEGRAM_CONFIG.get("enabled", False):
        return
    bot_token = TELEGRAM_CONFIG.get("bot_token")
    chat_id = TELEGRAM_CONFIG.get("chat_id")
    if not bot_token or not chat_id:
        print("⚠️ Telegram: missing bot_token/chat_id")
        return
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": message})
        if resp.status_code != 200:
            print(f"❌ Telegram Error: {resp.text}")
    except Exception as e:
        print(f"❌ Telegram send failed: {e}")

async def log_trade(symbol, side, amount, price):
    conn = get_db_connection(); cur = conn.cursor()
    try:
        cur.execute("INSERT INTO trades (symbol, side, amount, price) VALUES (%s, %s, %s, %s)",
                    (symbol, side, amount, price))
        conn.commit()
    except Exception as e:
        print(f"Error logging trade: {e}")
    finally:
        cur.close(); conn.close()

# ----------------- Indicators (unchanged) -----------------
def calculate_volatility(price_history, volatility_window):
    if len(price_history) < volatility_window:
        return 0.0
    recent_prices = list(price_history)[-volatility_window:]
    price_changes = np.diff(recent_prices) / recent_prices[:-1]
    return float(np.std(price_changes))

def calculate_moving_average(price_history, trend_window):
    if len(price_history) < trend_window:
        return None
    window_prices = price_history[-trend_window:]
    return sum(window_prices) / trend_window

def calculate_ema(prices, period, return_all=False):
    if len(prices) < period:
        return None if not return_all else []
    mult = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for p in prices[period:]:
        ema.append((p - ema[-1]) * mult + ema[-1])
    return ema if return_all else ema[-1]

def calculate_macd(prices, symbol, short_window=12, long_window=26, signal_window=9):
    if len(prices) < long_window + signal_window:
        print(f"⚠️ MACD data too short for {symbol}")
        return None, None, None
    s = calculate_ema(prices, short_window, True)
    l = calculate_ema(prices, long_window, True)
    macd_line = [sv - lv for sv, lv in zip(s, l)]
    signal = calculate_ema(macd_line, signal_window, True)
    hist = [m - si for m, si in zip(macd_line[-len(signal):], signal)]
    return macd_line[-1], signal[-1], hist[-1]

def calculate_rsi(prices, symbol, period=14):
    if len(prices) < period + 1:
        print(f"⚠️ RSI data too short for {symbol}")
        return None
    changes = np.diff(prices)
    gains = np.maximum(changes, 0)
    losses = np.maximum(-changes, 0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    rs = avg_gain / avg_loss if avg_loss != 0 else float('inf')
    return 100 - (100 / (1 + rs))

def calculate_long_term_ma(price_history, period=200):
    if len(price_history) < period:
        return None
    return sum(price_history[-period:]) / period

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
    s = pd.Series(prices)
    mid = s.rolling(window=period).mean()
    std = s.rolling(window=period).std()
    upper = mid + (num_std_dev * std)
    lower = mid - (num_std_dev * std)
    return mid.iloc[-1], upper.iloc[-1], lower.iloc[-1]

def save_weighted_avg_buy_price(symbol, avg_price):
    conn = get_db_connection(); cur = conn.cursor()
    if avg_price is not None:
        cur.execute(
            """
            INSERT INTO trading_state (symbol, initial_price, total_trades, total_profit)
            VALUES (%s, %s, 0, 0)
            ON CONFLICT (symbol) DO UPDATE
            SET initial_price = EXCLUDED.initial_price
            """,
            (symbol, avg_price)
        )
        print(f"💾  - {symbol} Weighted Average Buy Price Updated: {avg_price:.6f} {quote_currency}")
    conn.commit(); cur.close(); conn.close()

def get_weighted_avg_buy_price(symbol):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("""SELECT timestamp FROM trades WHERE symbol=%s AND side='SELL' ORDER BY timestamp DESC LIMIT 1""",(symbol,))
    row = cur.fetchone()
    last_sell_time = row[0] if row else None
    if last_sell_time:
        cur.execute("""SELECT amount, price FROM trades WHERE symbol=%s AND side='BUY' AND timestamp>%s""", (symbol, last_sell_time))
    else:
        cur.execute("SELECT amount, price FROM trades WHERE symbol=%s AND side='BUY'", (symbol,))
    buys = cur.fetchall()
    cur.close(); conn.close()
    if not buys: return None
    total_amount = sum(b[0] for b in buys)
    if total_amount == 0: return None
    return sum(a*p for a,p in buys) / total_amount

# ----------------- Manual commands -----------------
async def process_manual_commands(crypto_data):
    conn = get_db_connection(); cur = conn.cursor()
    cur.execute("SELECT id, symbol, action FROM manual_commands WHERE executed=FALSE")
    cmds = cur.fetchall()
    for cmd_id, symbol, action in cmds:
        action = action.upper()
        if symbol in crypto_data:
            crypto_data[symbol]["manual_cmd"] = action
            print(f"📥 Manual command: {action} for {symbol}")
        cur.execute("UPDATE manual_commands SET executed=TRUE WHERE id=%s", (cmd_id,))
        conn.commit()
    cur.close(); conn.close()

def _fmt(v, nd=6):
    try:
        return f"{v:.{nd}f}"
    except Exception:
        return str(v)

# ----------------- Trading Loop -----------------
crypto_data = {}
macd_confirmation = {symbol: {"buy": 0, "sell": 0} for symbol in crypto_symbols}

async def trading_bot():
    global crypto_data, macd_confirmation, quote_currency

    # init states
    for symbol in crypto_symbols:
        state = load_state(symbol)
        if state:
            crypto_data[symbol] = state
        else:
            initial_price = await exchange.get_price(symbol)
            if not initial_price:
                print(f"🚨 Failed to fetch initial {symbol} price. Skipping.")
                continue
            crypto_data[symbol] = {
                "price_history": deque([initial_price], maxlen=price_history_maxlen),
                "initial_price": initial_price,
                "total_trades": 0,
                "total_profit": 0.0,
            }
            save_state(symbol, initial_price, 0, 0.0)
            print(f"🔍 Monitoring {symbol}... Initial Price: {initial_price} {quote_currency}")

    while True:
        await asyncio.sleep(config["polling_interval"])

        # balances
        balances = await exchange.get_balances()
        update_balances_ex(balances, exchange.name)
        print("💰 Available Balances:")
        for ccy, bal in balances.items():
            print(f"  - {ccy}: {bal}")

        # update balances in DB
        update_balances_ex(balances, exchange.name)

        # prices
        prices = await asyncio.gather(*[exchange.get_price(s) for s in crypto_symbols])
        await process_manual_commands(crypto_data)

        for symbol, current_price in zip(crypto_symbols, prices):
            price_precision = coins_config[symbol]["precision"]["price"]
            if not current_price:
                print(f"🚨 {symbol}: No price data. Skipping."); continue
            if symbol not in crypto_data or not crypto_data[symbol]["price_history"]:
                print(f"🚨 {symbol}: Missing state. Skipping."); continue
            if current_price == crypto_data[symbol]["price_history"][-1]:
                print(f"🚨 {symbol}: Price unchanged ({current_price:.{price_precision}f}). Skipping."); continue

            save_price_history(symbol, current_price)
            crypto_data[symbol]["price_history"].append(current_price)
            price_history = list(crypto_data[symbol]["price_history"])
            previous_price = crypto_data[symbol].get("previous_price")

            # streaks
            if previous_price is not None:
                crypto_data[symbol]["rising_streak"] = crypto_data[symbol].get("rising_streak", 0) + 1 if current_price > previous_price else 0
                crypto_data[symbol]["falling_streak"] = crypto_data[symbol].get("falling_streak", 0) + 1 if current_price < previous_price else 0

            # per-coin settings
            cs = coins_config[symbol]
            buy_threshold = cs["buy_percentage"]
            sell_threshold = cs["sell_percentage"]
            rebuy_discount = cs["rebuy_discount"]
            volatility_window = cs["volatility_window"]
            trend_window = cs["trend_window"]
            macd_short_window = cs["macd_short_window"]
            macd_long_window = cs["macd_long_window"]
            macd_signal_window = cs["macd_signal_window"]
            rsi_period = cs["rsi_period"]
            trail_percent = cs.get("trail_percent", 0.5)

            if balances.get(symbol, 0.0) > 0 and current_price > crypto_data[symbol].get("peak_price", 0):
                crypto_data[symbol]["peak_price"] = current_price

            peak_price = crypto_data[symbol].get("peak_price")
            trail_stop_price = peak_price * (1 - trail_percent / 100) if peak_price else None

            needed = max(macd_long_window + macd_signal_window, rsi_period + 1)
            if len(price_history) < needed:
                print(f"⚠️ {symbol}: Not enough data for indicators. Need {needed}, have {len(price_history)}")
                continue

            long_term_ma = calculate_long_term_ma(price_history, period=200)
            if long_term_ma is None:
                print(f"⚠️ {symbol}: Not enough data for long-term MA. Skipping."); continue

            price_change = ((current_price - crypto_data[symbol]["initial_price"]) / crypto_data[symbol]["initial_price"]) * 100
            peak_display = f"${peak_price:.{price_precision}f}" if peak_price else "N/A"
            trail_display = f"${trail_stop_price:.{price_precision}f}" if trail_stop_price else "N/A"
            print(f"🚀 {symbol} - Price: ${current_price:.{price_precision}f} ({price_change:.2f}%), Peak: {peak_display}, Trail: {trail_display}")

            volatility = calculate_volatility(price_history, volatility_window)
            volatility_factor = min(1.5, max(0.5, 1 + abs(volatility)))
            moving_avg = calculate_moving_average(price_history, trend_window)

            macd_line, signal_line, macd_histogram = calculate_macd(price_history, symbol, macd_short_window, macd_long_window, macd_signal_window)
            rsi = calculate_rsi(price_history, symbol)

            crypto_data[symbol].setdefault("rsi_history", [])
            crypto_data[symbol]["rsi_history"].append(rsi)
            if len(crypto_data[symbol]["rsi_history"]) > 50:
                crypto_data[symbol]["rsi_history"].pop(0)

            k, d = calculate_stochastic_rsi(crypto_data[symbol]["rsi_history"])
            crypto_data[symbol]["stoch_k"] = k
            crypto_data[symbol]["stoch_d"] = d

            if k is not None and d is not None and (k < 0.2 and k > d):
                print(f"🔥 {symbol} StochRSI Buy: K={k:.2f}, D={d:.2f}")
            if k is not None and d is not None and (k > 0.8 and k < d):
                print(f"🔥 {symbol} StochRSI Sell: K={k:.2f}, D={d:.2f}")

            boll_mid, boll_up, boll_low = calculate_bollinger_bands(price_history)
            crypto_data[symbol]['bollinger'] = {'mid': boll_mid, 'upper': boll_up, 'lower': boll_low}
            boll_buy_signal = current_price < boll_low if boll_low else False
            boll_sell_signal = current_price > boll_up if boll_up else False

            dynamic_buy_threshold = buy_threshold * volatility_factor
            dynamic_sell_threshold = sell_threshold * volatility_factor

            actual_buy_price = get_weighted_avg_buy_price(symbol)

            if actual_buy_price is not None:
                expected_buy_price = actual_buy_price
                expected_sell_price = actual_buy_price * (1 + dynamic_sell_threshold / 100)
            else:
                expected_buy_price = crypto_data[symbol]["initial_price"] * (1 + dynamic_buy_threshold / 100)
                expected_sell_price = crypto_data[symbol]["initial_price"] * (1 + dynamic_sell_threshold / 100)

            if moving_avg and abs(current_price - moving_avg) < (0.05 * moving_avg) or crypto_data[symbol].get("manual_cmd") is not None:
                macd_buy = macd_line is not None and signal_line is not None and macd_line > signal_line
                rsi_buy = rsi is not None and rsi < 35
                macd_sell = macd_line is not None and signal_line is not None and macd_line < signal_line
                rsi_sell = rsi is not None and rsi > 65

                if macd_buy:
                    macd_confirmation[symbol]["buy"] += 1
                    macd_confirmation[symbol]["sell"] = max(0, macd_confirmation[symbol]["sell"] - 1)
                elif macd_sell:
                    macd_confirmation[symbol]["sell"] += 1
                    macd_confirmation[symbol]["buy"] = max(0, macd_confirmation[symbol]["buy"] - 1)
                else:
                    macd_confirmation[symbol]["buy"] = max(0, macd_confirmation[symbol]["buy"] - 1)
                    macd_confirmation[symbol]["sell"] = max(0, macd_confirmation[symbol]["sell"] - 1)

                time_since_last_buy = time.time() - crypto_data[symbol].get("last_buy_time", 0)

                if (time_since_last_buy > 900 and price_change >= dynamic_sell_threshold and
                    current_price > crypto_data[symbol]["initial_price"] * 1.05 and current_price > long_term_ma):
                    new_initial = 0.9 * crypto_data[symbol]["initial_price"] + 0.1 * long_term_ma
                    print(f"📈 {symbol} Adjust initial up: {crypto_data[symbol]['initial_price']:.{price_precision}f} → {new_initial:.{price_precision}f}")
                    crypto_data[symbol]["initial_price"] = new_initial
                    save_state(symbol, new_initial, crypto_data[symbol]["total_trades"], crypto_data[symbol]["total_profit"])

                elif (time_since_last_buy > 3600 and balances.get(symbol, 0) * current_price < 1 and
                      current_price < crypto_data[symbol]["initial_price"] * 0.95):
                    new_initial = 0.9 * crypto_data[symbol]["initial_price"] + 0.1 * current_price
                    print(f"📉 {symbol} Adjust initial down: {crypto_data[symbol]['initial_price']:.{price_precision}f} → {new_initial:.{price_precision}f}")
                    crypto_data[symbol]["initial_price"] = new_initial
                    save_state(symbol, new_initial, crypto_data[symbol]["total_trades"], crypto_data[symbol]["total_profit"])

                if boll_buy_signal:
                    print(f"💘 {symbol}: below Bollinger Lower — buy vibe")
                if boll_sell_signal:
                    print(f"💔 {symbol}: above Bollinger Upper — sell vibe")

                if actual_buy_price is not None and current_price > actual_buy_price * (1 + (dynamic_sell_threshold / 100)):
                    print(f"💵 {symbol}: above expected sell price ${expected_sell_price:.{price_precision}f} — sell signal!")

                price_slope = current_price - price_history[-3]

                cond_boll_primary = (boll_low is None or current_price < boll_low)
                cond_stoch_part = (k is None or d is None or (k < 0.2 and k > d))
                cond_boll_stoch = ((boll_mid is None or current_price < boll_mid) and cond_stoch_part)
                cond_entry_band = (cond_boll_primary or cond_boll_stoch)

                cond_price_thresh = (price_change <= dynamic_buy_threshold and actual_buy_price is None)
                cond_rebuy_discount = (actual_buy_price is not None and current_price < actual_buy_price * (1 - cs["rebuy_discount"] / 100.0))
                cond_trend = (current_price < long_term_ma)
                cond_cooldown = (time_since_last_buy > 120)
                cond_streak = (crypto_data[symbol].get("rising_streak", 0) > 1)
                cond_balance = (balances.get(quote_currency, 0) > 0)
                cond_manual = (crypto_data[symbol].get("manual_cmd") == "BUY")

                auto_buy = (cond_entry_band and (cond_price_thresh or cond_rebuy_discount) and cond_trend and cond_cooldown and cond_streak and cond_balance)
                buy_condition = (auto_buy or cond_manual)

                if DEBUG_MODE and not buy_condition and not cond_manual:
                    reasons = [
                        {"name":"Entry band","ok":cond_entry_band,"detail":f"need price<{_fmt(boll_low)} OR (price<{_fmt(boll_mid)} & bullish Stoch<0.2); price={_fmt(current_price)}; K={_fmt(k) if k is not None else 'None'}, D={_fmt(d) if d is not None else 'None'}"},
                        {"name":"Thresh/Discount","ok":(cond_price_thresh or cond_rebuy_discount),"detail":f"price_change={price_change:.2f}% vs dyn_buy={dynamic_buy_threshold:.2f}%"},
                        {"name":"Trend","ok":cond_trend,"detail":f"price={_fmt(current_price)} < long_MA={_fmt(long_term_ma)}"},
                        {"name":"Cooldown","ok":cond_cooldown,"detail":f"since_last_buy={int(time_since_last_buy)}s > 120s"},
                        {"name":"Rising streak","ok":cond_streak,"detail":f"streak={crypto_data[symbol].get('rising_streak', 0)} > 1"},
                        {"name":f"{quote_currency} balance","ok":cond_balance,"detail":f"{quote_currency}={_fmt(balances.get(quote_currency, 0), 2)} > 0"},
                    ]
                    print("🧰 BUY blocked for", symbol)
                    for r in reasons: print("  -", r["name"], ":", r["detail"])

                if buy_condition:
                    quote_avail = float(balances.get(quote_currency, 0))
                    quote_cost  = round(quote_avail * (SIZE_BUY_PCT / 100.0), 2)
                    if quote_cost < cs["min_order_sizes"]["buy"]:
                        print(f"🚫 Buy too small: ${quote_cost:.2f} (min: ${cs['min_order_sizes']['buy']})")
                        crypto_data[symbol]["manual_cmd"] = None
                    else:
                        buy_amount = quote_cost / current_price
                        print(f"💰 Buying {buy_amount:.6f} {symbol} (~{quote_cost:.2f} {quote_currency})")
                        resp = await exchange.place_market_order(symbol, "BUY", quote_amount=quote_cost)
                        if resp:
                            crypto_data[symbol]["manual_cmd"] = None
                            crypto_data[symbol]["total_trades"] += 1
                            crypto_data[symbol]["last_buy_time"] = time.time()
                            updated_avg = get_weighted_avg_buy_price(symbol)
                            save_weighted_avg_buy_price(symbol, updated_avg)
                            send_telegram_notification(f"✅ BOUGHT {buy_amount:.4f} {symbol} at ${current_price:.{price_precision}f} {quote_currency}")
                            crypto_data[symbol]["peak_price"] = current_price
                elif (
                    (
                        (
                            macd_sell and macd_confirmation[symbol]["sell"] >= 3 and
                            (k is None or d is None or (k > 0.8 and k < d)) and
                            (boll_up is None or current_price > boll_mid)
                        ) or
                        (boll_up is not None and current_price > boll_up)
                    ) and actual_buy_price is not None and
                    current_price > actual_buy_price * (1 + (dynamic_sell_threshold / 100)) and
                    crypto_data[symbol].get("falling_streak", 0) > 1 and
                    balances.get(symbol, 0) > 0
                ) or crypto_data[symbol].get("manual_cmd") == "SELL":
                    sell_pct    = SIZE_SELL_PCT / 100.0
                    precision   = cs["precision"]["amount"]
                    base_free   = float(balances.get(symbol, 0))
                    sell_amount = round(base_free * sell_pct, precision)
                    precision = cs["precision"]["amount"]
                    sell_amount = round(sell_amount, precision)
                    safe_margin = 10 ** -precision
                    sell_amount = min(sell_amount, balances.get(symbol, 0) - safe_margin)
                    if sell_amount > 0:
                        print(f"💵 Selling {sell_amount:.{precision}f} {symbol} at {current_price:.2f}!")
                        actual_buy_price = get_weighted_avg_buy_price(symbol)
                        resp = await exchange.place_market_order(symbol, "SELL", base_amount=sell_amount)
                        if resp:
                            crypto_data[symbol]["total_trades"] += 1
                            if actual_buy_price:
                                profit = (current_price - actual_buy_price) * sell_amount
                                crypto_data[symbol]["total_profit"] += profit
                                print(f"💰 {symbol} Profit: (Sell {current_price:.{price_precision}f} - Buy {actual_buy_price:.{price_precision}f}) * {sell_amount:.4f} = {profit:.2f} {quote_currency}")
                            else:
                                print("⚠️ No buy data; profit skipped.")
                            long_ma = long_term_ma
                            crypto_data[symbol]["initial_price"] = long_ma
                            print(f"🔄 {symbol} Initial reset to Long MA: {long_ma:.{price_precision}f}")
                            save_weighted_avg_buy_price(symbol, None)
                            send_telegram_notification(f"🚀 SOLD {sell_amount:.4f} {symbol} at ${current_price:.{price_precision}f} {quote_currency}")
                            crypto_data[symbol]["manual_cmd"] = None
                        else:
                            print("🚫 Sell order failed.")
            else:
                deviation = abs(current_price - moving_avg)
                deviation_pct = (deviation / moving_avg) * 100
                print(f"🔥 {symbol} Skipping: deviation {deviation_pct:.2f}% vs MA")
                print(f"📊 MA: {moving_avg:.{price_precision}f}, Price: {current_price:.{price_precision}f}")

            print(f"📊 {symbol} Avg buy: {get_weighted_avg_buy_price(symbol)} | Trades: {crypto_data[symbol]['total_trades']} | PnL: ${crypto_data[symbol]['total_profit']:.2f}")
            crypto_data[symbol]["manual_cmd"] = None
            save_state(symbol, crypto_data[symbol]["initial_price"], crypto_data[symbol]["total_trades"], crypto_data[symbol]["total_profit"])
            crypto_data[symbol]["previous_price"] = current_price

if __name__ == "__main__":
    asyncio.run(trading_bot())
