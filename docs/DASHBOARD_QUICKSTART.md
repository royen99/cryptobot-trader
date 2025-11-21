# Dashboard Quick Start Guide 🚀

Get your trading dashboard up and running in 5 minutes.

## Prerequisites

- Docker & Docker Compose installed
- `config.json` with your Coinbase API credentials
- PostgreSQL database (included in docker-compose)

---

## Step 1: Update Docker Compose

If you're already running the bot, update your `docker-compose.yml` to include the dashboard:

```yaml
version: "3.9"

services:
  trader:
    image: royen99/cryptobot-trader:latest
    restart: unless-stopped
    environment:
      CONFIG_PATH: /config/config.json
      REQUEST_HOST: api.coinbase.com
      DEBUG_MODE: "false"
    volumes:
      - ./config.json:/config/config.json:ro
    depends_on:
      - postgres

  dashboard:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      # Database connection (no config.json needed! 🎉)
      DB_HOST: db
      DB_PORT: 5432
      DB_NAME: cryptobot
      DB_USER: cryptobot
      DB_PASSWORD: your_secure_password_here
    depends_on:
      - postgres

  postgres:
    image: postgres:14-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: cryptobot
      POSTGRES_USER: cryptobot
      POSTGRES_PASSWORD: your_secure_password_here
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init_db.sql:/docker-entrypoint-initdb.d/init.sql:ro
    ports:
      - "5432:5432"

volumes:
  postgres_data:
```

---

## Step 2: Apply Database Migration

If you're upgrading from the old JSON-based config:

```bash
# Connect to your database
psql -h localhost -U cryptobot -d cryptobot

# Run the migration
\i migrations/001_add_coin_settings.sql

# Verify it worked
SELECT symbol, enabled, buy_percentage, sell_percentage FROM coin_settings;
```

Expected output: ETH and XRP with their settings.

---

## Step 3: Start the Dashboard

```bash
# Build and start all services
docker-compose up -d

# Check logs to ensure everything started
docker-compose logs -f dashboard
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000
INFO:     Application startup complete.
```

---

## Step 4: Access the Dashboard

Open your browser to:
```
http://localhost:8000
```

You should see:
- **Stats cards**: Total profit, trades, balances
- **Holdings table**: Current positions with P&L
- **Coin settings**: All configured coins with edit buttons
- **Recent trades**: Latest buy/sell executions

---

## Step 5: Test Configuration Changes

1. **Edit a coin's settings:**
   - Click **Edit** next to ETH
   - Change `Buy %` to `-4`
   - Change `Sell %` to `4`
   - Click **Save Changes**

2. **Restart the trading bot** to apply:
   ```bash
   docker-compose restart trader
   ```

3. **Verify in logs:**
   ```bash
   docker-compose logs -f trader | grep "Expected Prices"
   ```

   You should see the new thresholds reflected.

---

## Step 6: Test Manual Trading

1. **Queue a manual command:**
   - Find XRP in the **Coin Settings** table
   - Click **Buy** button
   - Confirm the action

2. **Check manual commands table:**
   ```sql
   SELECT * FROM manual_commands WHERE executed = FALSE;
   ```

   You should see your command queued.

3. **Watch bot logs:**
   ```bash
   docker-compose logs -f trader
   ```

   Within ~30 seconds you'll see:
   ```
   📥 Manual command received: BUY for XRP
   ```

---

## Common Issues

### Dashboard shows "Loading..." forever

**Fix:**
```bash
# Check API health
curl http://localhost:8000/health

# Check database connection
docker exec -it postgres psql -U cryptobot -c "SELECT COUNT(*) FROM coin_settings;"
```

### "Database connection failed"

**Fix:**
```bash
# Verify postgres is running
docker ps | grep postgres

# Check credentials in config.json match docker-compose.yml
cat config.json | grep database -A5
```

### Changes not applied after editing

**Reminder:** You must restart the trading bot for config changes to take effect:
```bash
docker-compose restart trader
```

(Future enhancement: hot-reload endpoint)

---

## Next Steps

- **Customize the UI**: Edit `dashboard/templates/dashboard.html`
- **Add charts**: Integrate Chart.js for price history visualization
- **Secure it**: Add authentication, HTTPS reverse proxy
- **Explore API**: See `dashboard/README.md` for full endpoint reference

Happy trading! 🚀
