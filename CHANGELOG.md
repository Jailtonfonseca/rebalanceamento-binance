# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-09-06

### Added
- **Initial Release**
- Core application skeleton and structure.
- Configuration management with UI, including encryption for API keys.
- Binance and CoinMarketCap API clients with async requests and retry logic.
- Core rebalancing engine to calculate trades based on target allocations.
- Rebalance executor with Dry Run and Live modes, and concurrency locking.
- Web UI for Dashboard, Configuration, and History pages using FastAPI and Jinja2.
- Manual rebalance trigger via UI and API.
- Periodic rebalancing via a background scheduler (APScheduler).
- SQLite database for persisting rebalancing history.
- Unit and integration tests for core business logic.
- Dockerfile and Docker Compose setup for easy deployment.
- Comprehensive README documentation and helper scripts.
