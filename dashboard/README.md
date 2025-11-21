# CryptoBot Trading Dashboard 📊

Modern web-based monitoring and configuration interface for your trading bot. Because clicking beats SQL and YAML never lies 😜

![Dashboard Preview](https://via.placeholder.com/1200x600/667eea/ffffff?text=CryptoBot+Dashboard)

## Features 🚀

### Real-Time Monitoring
- **💼 Holdings Overview**: Live portfolio value with unrealized P&L per coin
- **📊 Trade History**: Recent buy/sell activity with timestamps
- **💰 Performance Stats**: Total profit, trade counts, active coins
- **📈 Price Tracking**: Historical price data (future: charts with Chart.js)

### Configuration Management
- **⚙️ Coin Settings Editor**: Adjust buy/sell thresholds, windows, precision
- **🔘 Enable/Disable Coins**: Toggle trading per coin without code changes
- **🎯 Manual Trading**: Send immediate BUY/SELL commands to the bot
- **✅ Live Updates**: Changes reflected in real-time (auto-refresh every 30s)

### Tech Stack
- **Backend**: FastAPI (Python) - blazing fast async API
- **Frontend**: Vanilla HTML/CSS/JS - lightweight, no build step
- **Database**: Shared PostgreSQL with trading bot
- **Deployment**: Separate Docker container for isolation

---

## Quick Start

### Using Docker Compose (Recommended)

The dashboard is included in `docker-compose-sample.yml`:

```bash
# Copy and customize the sample
cp docker-compose-sample.yml docker-compose.yml

# Start all services (trader + dashboard + postgres)
docker-compose up -d

# Access dashboard at http://localhost:8000
open http://localhost:8000
```

### Manual Build

```bash
cd dashboard

# Build the dashboard image
docker build -t cryptobot-dashboard .

# Run the dashboard (ensure DB is accessible)
docker run -d \
  -p 8000:8000 \
  -e DB_HOST=postgres \
  -e DB_PORT=5432 \
  -e DB_NAME=cryptobot \
  -e DB_USER=trader \
  -e DB_PASSWORD=your_password \
  --name cryptobot-dashboard \
  cryptobot-dashboard
```

### Development Mode

```bash
cd dashboard

# Install dependencies
pip install -r requirements.txt

# Run with hot-reload
uvicorn main:app --reload --port 8000
```

---

## API Endpoints 🔌

### Overview & Stats
- `GET /api/overview` - High-level stats (profit, trades, balances)
- `GET /api/stats/summary` - Performance breakdown per coin

### Holdings & Trades
- `GET /api/holdings` - Current portfolio with P&L
- `GET /api/trades/recent?limit=50` - Recent trade history
- `GET /api/price-history/{symbol}?hours=24` - Price chart data

### Coin Configuration
- `GET /api/coins` - List all coin settings
- `PATCH /api/coins/{symbol}` - Update coin settings (partial)
- `POST /api/coins/{symbol}/toggle` - Enable/disable coin

### Manual Trading
- `POST /api/manual-command` - Queue BUY/SELL command
  ```json
  {
    "symbol": "ETH",
    "action": "BUY"
  }
  ```

### Health Check
- `GET /health` - Service health status

---

## Configuration

The dashboard reads database connection details from **environment variables only** (no config.json needed! 🎉):

**Environment Variables:**
- `DB_HOST` - Database hostname (default: `localhost`)
- `DB_PORT` - Database port (default: `5432`)
- `DB_NAME` - Database name (default: `cryptobot`)
- `DB_USER` - Database user (default: `trader`)
- `DB_PASSWORD` - Database password (default: `changeme`)

These are automatically set in `docker-compose.yml` to match the PostgreSQL service

---

## Usage Examples

### Adjust Buy/Sell Thresholds

1. Navigate to **Coin Settings** section
2. Click **Edit** button for desired coin
3. Update `Buy %` and `Sell %` values
4. Click **Save Changes**
5. **Restart trading bot** to apply (or implement hot-reload)

### Manual Trade Execution

1. Find coin in **Coin Settings** table
2. Click **Buy** or **Sell** button
3. Confirm the action
4. Bot will execute on next cycle (~25s)

### Enable/Disable Coin Trading

1. Click **Enable** or **Disable** button next to coin
2. Restart bot to stop trading disabled coins

---

## Screenshots

### Holdings Dashboard
Shows real-time portfolio value, profit/loss per position, and weighted average buy prices.

### Coin Settings Editor
Modal-based form for tweaking technical indicator windows, thresholds, and precision settings.

### Recent Trades
Chronological feed of buy/sell executions with amounts and prices.

---

## Architecture

```
┌─────────────────┐
│  Web Browser    │
│  (Dashboard UI) │
└────────┬────────┘
         │ HTTP/JSON
         ▼
┌─────────────────┐      ┌──────────────┐
│  FastAPI App    │◄────►│  PostgreSQL  │
│  (main.py)      │      │  (Shared DB) │
└─────────────────┘      └──────┬───────┘
                                 │
                                 ▼
                         ┌──────────────┐
                         │ Trading Bot  │
                         │ (main.py)    │
                         └──────────────┘
```

**Data Flow:**
1. Dashboard reads from shared PostgreSQL tables
2. User updates coin settings via API
3. Trading bot reads updated settings on next cycle
4. Trades are logged to DB → dashboard reflects changes

**Isolation:**
- Dashboard runs in separate container
- Read-only access to most tables
- Write access only to `coin_settings` and `manual_commands`

---

## Security Considerations 🔒

### Production Deployment Checklist

- [ ] **Change default passwords** in `config.json` and `docker-compose.yml`
- [ ] **Use HTTPS** (reverse proxy with Nginx/Caddy + Let's Encrypt)
- [ ] **Restrict CORS origins** in `main.py` (remove `allow_origins=["*"]`)
- [ ] **Add authentication** (basic auth, OAuth, or API keys)
- [ ] **Firewall rules** to limit dashboard access to trusted IPs
- [ ] **Environment variables** for secrets (don't commit `config.json`)

### Example Nginx Reverse Proxy

```nginx
server {
    listen 443 ssl;
    server_name dashboard.yourbot.com;
    
    ssl_certificate /etc/letsencrypt/live/yourbot.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourbot.com/privkey.pem;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## Customization 🎨

### Change Dashboard Theme

Edit `templates/dashboard.html` CSS variables:

```css
body {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}

.card {
    background: white;
    border-radius: 12px;
}
```

### Add Price Charts

Integrate Chart.js (already included via CDN):

```javascript
async function renderPriceChart(symbol) {
    const res = await fetch(`/api/price-history/${symbol}?hours=24`);
    const data = await res.json();
    
    const ctx = document.getElementById('price-chart').getContext('2d');
    new Chart(ctx, {
        type: 'line',
        data: {
            labels: data.history.map(h => new Date(h.timestamp).toLocaleTimeString()),
            datasets: [{
                label: `${symbol} Price`,
                data: data.history.map(h => h.price),
                borderColor: '#667eea',
                tension: 0.4
            }]
        }
    });
}
```

### Add Telegram Notifications for Config Changes

In `main.py`, after updating coin settings:

```python
from app.main import send_telegram_notification  # Import from trader bot

@app.patch("/api/coins/{symbol}")
async def update_coin_settings(symbol: str, updates: CoinSettingsUpdate):
    # ... existing code ...
    
    send_telegram_notification(
        f"⚙️ Config Updated: {symbol} settings changed via dashboard"
    )
```

---

## Troubleshooting 🔧

### Dashboard Won't Start

**Symptom:** Container crashes on startup

**Fix:**
1. Check logs: `docker logs cryptobot-dashboard`
2. Verify `config.json` is mounted: `docker exec cryptobot-dashboard ls /config`
3. Ensure PostgreSQL is reachable: `docker exec cryptobot-dashboard ping postgres`

### Database Connection Error

**Symptom:** `500 Internal Server Error` on all API calls

**Fix:**
1. Verify DB credentials in `config.json`
2. Check postgres service is running: `docker ps | grep postgres`
3. Test connection: `psql -h localhost -U cryptobot -d cryptobot`

### Empty Holdings Table

**Symptom:** "Loading holdings..." never resolves

**Fix:**
1. Check browser console for errors (F12)
2. Verify API endpoint: `curl http://localhost:8000/api/holdings`
3. Ensure `balances` table has data: `SELECT * FROM balances;`

### Manual Commands Not Executing

**Symptom:** Commands queued but bot doesn't execute

**Fix:**
1. Check `manual_commands` table: `SELECT * FROM manual_commands WHERE executed = FALSE;`
2. Verify trading bot is running and polling DB
3. Ensure symbol matches exactly (case-sensitive)

---

## Future Enhancements 🚧

### Planned Features
- [ ] **Price Charts**: Historical price visualization with Chart.js
- [ ] **Profit/Loss Charts**: Daily/weekly performance graphs
- [ ] **Live Order Book**: Real-time buy/sell targets per coin
- [ ] **Alert Configuration**: Custom price/profit notifications
- [ ] **Strategy Backtesting**: Simulate settings on historical data
- [ ] **Multi-Bot Support**: Manage multiple trading bot instances
- [ ] **Mobile Responsive**: Optimized UI for phones/tablets
- [ ] **Dark Mode**: Because traders trade at night 🌙

### Contributions Welcome!
Open an issue or PR if you'd like to add features. Check `CONTRIBUTING.md` for guidelines.

---

## Performance Notes ⚡

- **Auto-refresh**: Dashboard polls API every 30s (configurable in JS)
- **Database Load**: Read-only queries are lightweight (indexed tables)
- **Concurrent Users**: FastAPI handles 100+ users on 1 CPU core
- **Memory Footprint**: ~50MB per container (Python 3.11 slim base)

---

## License

MIT License - Same as main trading bot project.

---

## Support & Community

- **Issues**: [GitHub Issues](https://github.com/royen99/cryptobot-trader/issues)
- **Docs**: [Main README](../README.md)
- **Donations**: See main README for crypto addresses

Happy trading! 🚀 Let's yeet those gains to the moon! 🌙
