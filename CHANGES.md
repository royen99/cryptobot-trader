# Changes

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [19/11/2025]

### Added
- **Database-driven coin configuration**: Coin-specific settings moved from `config.json` to new `coin_settings` table.
- **Web Dashboard**: FastAPI-based monitoring and configuration UI (`dashboard/` directory).
  - Real-time holdings with unrealized P&L tracking
  - Coin settings editor (adjust thresholds without SQL)
  - Manual BUY/SELL command interface
  - Recent trades history viewer
  - Performance stats and portfolio overview
  - Auto-refresh every 30 seconds
- Migration script: `migrations/001_add_coin_settings.sql` for existing databases.
- Migration README with management examples and rollback instructions.
- Auto-update trigger for `coin_settings.updated_at` timestamp.
- Dashboard Dockerfile and requirements.txt for containerized deployment.
- Updated `docker-compose-sample.yml` with dashboard service + PostgreSQL.

### Changed
- `main.py` now loads coin configuration from database via `load_coins_config_from_db()`.
- `init_db.sql` updated to include `coin_settings` table with ETH/XRP seed data.
- `config.json.template` deprecates `coins` section with migration notice.
- Main README updated with dashboard quick-start guide.

### Benefits
- Runtime reconfigurability: Tweak thresholds without restarting the bot 🚀
- Add/remove coins via SQL instead of code edits
- Audit trail for config changes with timestamps
- Enable/disable coins on-the-fly
- Web UI eliminates need for SQL knowledge (clicking beats SQL 😜)

## [15/08/2025]

### Added
- Donation section to README.md files for both trader and monitor.
- Explainer for configuration options in README.md.

### Changed
- Add Network/Retry logic in the API calls.
- Improve error handling and logging for API requests.
- Add a changelog file to the project 🚀
