"""
CryptoBot Trading Dashboard 📊
FastAPI backend for monitoring and configuring the trading bot.
Because clicking beats SQL (and YAML never lies 😜)
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta

app = FastAPI(title="CryptoBot Dashboard", version="1.0.0")

# CORS for dev (tighten in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load database connection from environment variables (no config.json needed! 🎉)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "cryptobot")
DB_USER = os.getenv("DB_USER", "trader")
DB_PASSWORD = os.getenv("DB_PASSWORD", "changeme")

def get_db_connection():
    """Get a fresh database connection. Remember to close it when done! 🔌"""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )

def get_quote_currency():
    """Read quote currency from config.json based on selected exchange."""
    import json
    config_path = os.getenv("CONFIG_PATH", "/config/config.json")
    try:
        with open(config_path, "r") as f:
            config = json.load(f)
            selected_exchange = config.get("selected_exchange", "coinbase")
            exchange_config = config.get("exchange", {}).get(selected_exchange, {})
            return exchange_config.get("quote_currency", "USDC")
    except Exception as e:
        print(f"⚠️ Failed to read quote currency from config: {e}")
        return "USDC"  # Default fallback

# Pydantic models for request validation
class CoinSettingsUpdate(BaseModel):
    buy_percentage: Optional[float] = None
    sell_percentage: Optional[float] = None
    rebuy_discount: Optional[float] = None
    volatility_window: Optional[int] = None
    trend_window: Optional[int] = None
    macd_short_window: Optional[int] = None
    macd_long_window: Optional[int] = None
    macd_signal_window: Optional[int] = None
    rsi_period: Optional[int] = None
    trail_percent: Optional[float] = None
    min_order_buy: Optional[float] = None
    min_order_sell: Optional[float] = None
    precision_price: Optional[int] = None
    precision_amount: Optional[int] = None
    enabled: Optional[bool] = None

class ManualCommand(BaseModel):
    symbol: str
    action: str  # "BUY" or "SELL"

# Serve static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

@app.get("/")
async def dashboard(request: Request):
    """Serve main dashboard HTML."""
    return templates.TemplateResponse("dashboard.html", {"request": request})

@app.get("/api/overview")
async def get_overview():
    """Get high-level overview: total value, P&L, active trades."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Get current balances
        cursor.execute("SELECT currency, available_balance FROM balances")
        balances = {row["currency"]: float(row["available_balance"]) for row in cursor.fetchall()}
        
        # Get trading state (profit tracking)
        cursor.execute("SELECT symbol, initial_price, total_trades, total_profit FROM trading_state")
        trading_state = cursor.fetchall()
        
        total_profit = sum(float(row["total_profit"] or 0) for row in trading_state)
        total_trades = sum(int(row["total_trades"] or 0) for row in trading_state)
        
        # Get enabled coins count
        cursor.execute("SELECT COUNT(*) as count FROM coin_settings WHERE enabled = TRUE")
        active_coins = cursor.fetchone()["count"]
        
        # Get quote currency from config
        quote_currency = get_quote_currency()
        
        return {
            "balances": balances,
            "total_profit_usdc": round(total_profit, 2),
            "total_trades": total_trades,
            "active_coins": active_coins,
            "quote_currency": quote_currency,
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        cursor.close()
        conn.close()

@app.get("/api/holdings")
async def get_holdings():
    """Get current holdings with live prices and P&L."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Get balances
        cursor.execute("SELECT currency, available_balance FROM balances WHERE available_balance > 0")
        holdings = []
        
        for row in cursor.fetchall():
            symbol = row["currency"]
            balance = float(row["available_balance"])
            
            # Skip USDC (it's the quote currency)
            if symbol == "USDC":
                holdings.append({
                    "symbol": "USDC",
                    "balance": balance,
                    "current_price": 1.0,
                    "value_usdc": balance,
                    "avg_buy_price": None,
                    "unrealized_pnl": 0,
                    "pnl_percent": 0
                })
                continue
            
            # Get latest price from price_history
            cursor.execute("""
                SELECT price FROM price_history 
                WHERE symbol = %s 
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (symbol,))
            price_row = cursor.fetchone()
            current_price = float(price_row["price"]) if price_row else 0
            
            # Get weighted avg buy price from trades
            cursor.execute("""
                SELECT timestamp FROM trades 
                WHERE symbol = %s AND side = 'SELL' 
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (symbol,))
            last_sell = cursor.fetchone()
            last_sell_time = last_sell["timestamp"] if last_sell else None
            
            if last_sell_time:
                cursor.execute("""
                    SELECT amount, price FROM trades 
                    WHERE symbol = %s AND side = 'BUY' 
                    AND timestamp > %s
                """, (symbol, last_sell_time))
            else:
                cursor.execute("""
                    SELECT amount, price FROM trades 
                    WHERE symbol = %s AND side = 'BUY'
                """, (symbol,))
            
            buy_trades = cursor.fetchall()
            avg_buy_price = None
            unrealized_pnl = 0
            pnl_percent = 0
            
            if buy_trades:
                total_amount = sum(float(t["amount"]) for t in buy_trades)
                if total_amount > 0:
                    avg_buy_price = sum(float(t["amount"]) * float(t["price"]) for t in buy_trades) / total_amount
                    unrealized_pnl = (current_price - avg_buy_price) * balance
                    pnl_percent = ((current_price - avg_buy_price) / avg_buy_price * 100) if avg_buy_price > 0 else 0
            
            holdings.append({
                "symbol": symbol,
                "balance": round(balance, 6),
                "current_price": round(current_price, 2),
                "value_usdc": round(balance * current_price, 2),
                "avg_buy_price": round(avg_buy_price, 6) if avg_buy_price else None,
                "unrealized_pnl": round(unrealized_pnl, 2),
                "pnl_percent": round(pnl_percent, 2)
            })
        
        return {"holdings": holdings}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/coins")
async def get_coin_settings():
    """Get all coin settings (for config table)."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT symbol, enabled, buy_percentage, sell_percentage, rebuy_discount,
                   volatility_window, trend_window, macd_short_window, macd_long_window,
                   macd_signal_window, rsi_period, trail_percent,
                   min_order_buy, min_order_sell, precision_price, precision_amount,
                   updated_at
            FROM coin_settings
            ORDER BY symbol
        """)
        coins = []
        for row in cursor.fetchall():
            coins.append({
                "symbol": row["symbol"],
                "enabled": row["enabled"],
                "buy_percentage": float(row["buy_percentage"]),
                "sell_percentage": float(row["sell_percentage"]),
                "rebuy_discount": float(row["rebuy_discount"]),
                "volatility_window": row["volatility_window"],
                "trend_window": row["trend_window"],
                "macd_short_window": row["macd_short_window"],
                "macd_long_window": row["macd_long_window"],
                "macd_signal_window": row["macd_signal_window"],
                "rsi_period": row["rsi_period"],
                "trail_percent": float(row["trail_percent"]),
                "min_order_buy": float(row["min_order_buy"]),
                "min_order_sell": float(row["min_order_sell"]),
                "precision_price": row["precision_price"],
                "precision_amount": row["precision_amount"],
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None
            })
        return {"coins": coins}
    finally:
        cursor.close()
        conn.close()

@app.patch("/api/coins/{symbol}")
async def update_coin_settings(symbol: str, updates: CoinSettingsUpdate):
    """Update coin settings (partial update)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Build dynamic UPDATE query for provided fields only
        update_fields = []
        values = []
        for field, value in updates.dict(exclude_none=True).items():
            update_fields.append(f"{field} = %s")
            values.append(value)
        
        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")
        
        values.append(symbol)
        query = f"UPDATE coin_settings SET {', '.join(update_fields)} WHERE symbol = %s"
        cursor.execute(query, values)
        conn.commit()
        
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Coin {symbol} not found")
        
        return {"status": "success", "message": f"Updated {symbol} settings"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cursor.close()
        conn.close()

@app.post("/api/coins/{symbol}/toggle")
async def toggle_coin(symbol: str):
    """Enable/disable a coin."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        cursor.execute("SELECT enabled FROM coin_settings WHERE symbol = %s", (symbol,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Coin {symbol} not found")
        
        new_state = not row["enabled"]
        cursor.execute("UPDATE coin_settings SET enabled = %s WHERE symbol = %s", (new_state, symbol))
        conn.commit()
        
        return {"status": "success", "symbol": symbol, "enabled": new_state}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/trades/recent")
async def get_recent_trades(limit: int = 50):
    """Get recent trades."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        cursor.execute("""
            SELECT id, symbol, side, amount, price, timestamp
            FROM trades
            ORDER BY timestamp DESC
            LIMIT %s
        """, (limit,))
        
        trades = []
        for row in cursor.fetchall():
            trades.append({
                "id": row["id"],
                "symbol": row["symbol"],
                "side": row["side"],
                "amount": float(row["amount"]),
                "price": float(row["price"]),
                "value_usdc": round(float(row["amount"]) * float(row["price"]), 2),
                "timestamp": row["timestamp"].isoformat()
            })
        return {"trades": trades}
    finally:
        cursor.close()
        conn.close()

@app.get("/api/price-history/{symbol}")
async def get_price_history(symbol: str, hours: int = 24):
    """Get price history for charting."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        cursor.execute("""
            SELECT timestamp, price
            FROM price_history
            WHERE symbol = %s AND timestamp > %s
            ORDER BY timestamp ASC
        """, (symbol, cutoff))
        
        history = []
        for row in cursor.fetchall():
            history.append({
                "timestamp": row["timestamp"].isoformat(),
                "price": float(row["price"])
            })
        return {"symbol": symbol, "history": history}
    finally:
        cursor.close()
        conn.close()

@app.post("/api/manual-command")
async def create_manual_command(command: ManualCommand):
    """Create a manual BUY/SELL command for the bot to execute."""
    if command.action.upper() not in ["BUY", "SELL"]:
        raise HTTPException(status_code=400, detail="Action must be BUY or SELL")
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO manual_commands (symbol, action, executed)
            VALUES (%s, %s, FALSE)
        """, (command.symbol, command.action.upper()))
        conn.commit()
        
        return {
            "status": "success",
            "message": f"{command.action} command queued for {command.symbol}. Bot will execute on next cycle."
        }
    finally:
        cursor.close()
        conn.close()

@app.get("/api/stats/summary")
async def get_stats_summary():
    """Get performance stats summary."""
    conn = get_db_connection()
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # Total profit per coin
        cursor.execute("""
            SELECT symbol, total_profit, total_trades
            FROM trading_state
            WHERE total_trades > 0
            ORDER BY total_profit DESC
        """)
        coin_stats = []
        for row in cursor.fetchall():
            coin_stats.append({
                "symbol": row["symbol"],
                "total_profit": round(float(row["total_profit"] or 0), 2),
                "total_trades": row["total_trades"]
            })
        
        # Trades by day (last 7 days)
        cursor.execute("""
            SELECT DATE(timestamp) as date, COUNT(*) as count
            FROM trades
            WHERE timestamp > NOW() - INTERVAL '7 days'
            GROUP BY DATE(timestamp)
            ORDER BY date ASC
        """)
        daily_trades = [{"date": str(row["date"]), "count": row["count"]} for row in cursor.fetchall()]
        
        return {
            "coin_performance": coin_stats,
            "daily_trades": daily_trades
        }
    finally:
        cursor.close()
        conn.close()

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
