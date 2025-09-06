# Crypto Portfolio Rebalancing Bot

A fully-featured, containerized bot to automatically rebalance your cryptocurrency portfolio on Binance. It provides a simple web interface for configuration, status monitoring, and manual control, using market data from CoinMarketCap to inform its decisions.

![Dashboard Screenshot](https://i.imgur.com/your-screenshot-url.png) <!-- Placeholder for a future screenshot -->

## Technology Stack

- **Backend**: FastAPI
- **Frontend**: Jinja2 (Server-Side Rendered)
- **Database**: SQLite
- **API Clients**: HTTPX, Tenacity
- **Security**: Cryptography (Fernet), Bcrypt
- **Scheduling**: APScheduler
- **Containerization**: Docker & Docker Compose

---

## How It Works

The bot follows a clear, logical process to rebalance your portfolio:

1.  **Fetch Data**: It fetches your current asset balances from Binance and the list of top-ranked cryptocurrencies from CoinMarketCap.
2.  **Filter Assets**: It determines which of your assets are eligible for rebalancing by finding the intersection of your wallet, your target allocations, and the top-ranked list from CoinMarketCap. This prevents trading irrelevant or low-quality assets.
3.  **Calculate Current State**: It calculates the total value of your eligible portfolio in your chosen base currency (e.g., USDT).
4.  **Generate a Plan**: It compares your current allocations to your target allocations and calculates the trades (buys/sells) needed to close the gap.
5.  **Validate Trades**: Each proposed trade is validated against Binance's official trading rules (`minNotional`, `stepSize`) and your configured minimum trade value. Trades that are too small are discarded.
6.  **Execute**: If not in "Dry Run" mode, the bot executes the validated trades on Binance. `SELL` orders are always processed before `BUY` orders to ensure funds are available.

---

## Features

- **Web UI**: Easy-to-use interface for all configuration, served directly from the container.
- **Flexible Strategies**: Rebalance periodically (e.g., every 24 hours) or based on a deviation threshold.
- **Dry Run Mode**: Simulate rebalancing runs without executing any real trades to see the plan first.
- **Binance Integration**: Connects to your Binance account to read balances, get prices, and execute market orders.
- **CoinMarketCap Integration**: Filters your portfolio against top-ranked assets to avoid rebalancing low-quality or delisted coins.
- **Secure**: API keys are encrypted at rest using a `MASTER_KEY`. The bot never exposes your keys, not even in the UI.
- **Persistent**: All configuration and history are saved to a local `./data` directory, surviving container restarts.
- **Dockerized**: Runs in a single, lightweight Docker container for easy deployment.
- **Observability**: Provides structured JSON logs, a history page, and a `/metrics` endpoint for Prometheus.

---

## 🛑 Security Warning

- **MASTER_KEY**: This application uses a `MASTER_KEY` to encrypt your API credentials. The first time you run the bot, a key will be generated in `data/secret.key`. You **MUST** back up this key. For any future deployments or if you move your `data` directory, you must provide this exact key as an environment variable to be able to decrypt your saved settings. **If you lose this key, you will have to re-enter all your credentials.**
- **HTTPS**: This application serves HTTP by default. Do not expose it directly to the internet. In a production environment, you should always run it behind a reverse proxy like Nginx or Traefik that provides TLS/SSL encryption (HTTPS).

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### 1. Configuration

Before running the application, you need to set up your master encryption key. Create a file named `.env` in the same directory as `docker-compose.yml`.

If this is your **first time** running the bot, you can leave the key empty to have one generated for you:
```env
# .env file
MASTER_KEY=
```
The bot will create a `data/secret.key` file. You should then copy the content of this file and place it in the `MASTER_KEY` variable for all future runs.

If you **already have a key**, paste it here:
```env
# .env file
MASTER_KEY=your_super_secret_and_long_encryption_key_here
```

### 2. Build and Run

With Docker running, execute the following command in your terminal:

```bash
docker-compose up --build -d
```
This will build the Docker image and start the container in detached mode. To view logs, you can run `docker-compose logs -f`.

### 3. Access the UI

Once the container is running, open your web browser and navigate to: **http://localhost:8080**

The default login credentials are:
- **Username**: `admin`
- **Password**: `admin`

> **Note**: You should change the password immediately via the Configuration page.

---

## UI and Configuration Guide

The web interface has three main sections: **Dashboard**, **Configuration**, and **History**.

### Configuration Page

This is where you control the bot's behavior.

| Setting | Description |
| :--- | :--- |
| **Change Admin Password** | Update the password used to access the web UI. |
| **Binance API Key / Secret** | Your API credentials from Binance. Required for all trading operations. |
| **CoinMarketCap API Key** | Your API key from CoinMarketCap. Required to fetch asset rankings. |
| **Dry Run Mode** | **Enabled**: Simulates trades and generates a report. No real orders are placed. **Disabled**: Executes real trades on your Binance account. |
| **Strategy Type** | **Periodic**: Rebalances automatically at a fixed interval (e.g., every 24 hours). **Threshold**: Rebalances only when an asset's allocation deviates by a certain percentage (not yet implemented). |
| **Periodic Interval (Hours)** | If using the Periodic strategy, this sets how often the bot will run. |
| **Rebalance Threshold (%)**| If using the Threshold strategy, this is the deviation percentage that triggers a rebalance. |
| **Base Pair** | The currency to use for all trades and value calculations (e.g., `USDT`, `BUSD`). |
| **Max CoinMarketCap Rank** | The bot will only consider assets that are within this rank on CoinMarketCap. |
| **Minimum Trade Value (USD)** | The bot will ignore any potential trades with a total value below this amount. Prevents tiny, insignificant trades. |
| **Target Allocations** | Define your ideal portfolio. The percentages must add up to 100%. You can add or remove assets dynamically. |

---

## Development

### Running Tests

To run the unit and integration tests, execute the following command from the root directory:

```bash
PYTHONPATH=src pytest
```

### API Documentation

The application provides automatic API documentation via Swagger UI and ReDoc. Once the application is running, you can access them at:
- **Swagger UI**: http://localhost:8080/docs
- **ReDoc**: http://localhost:8080/redoc

---

## Helper Scripts

The `scripts/` directory contains helper scripts for administrative tasks. They should be run from the root of the project.

- **`backup_db.sh`**: Creates a compressed, timestamped backup of your database file (`data/rebalancer.db`) and stores it in the `data/backups` directory.
  ```bash
  ./scripts/backup_db.sh
  ```

- **`reset_password.sh`**: Resets the admin password. This is useful if you get locked out. It must be run while the container is running.
  ```bash
  ./scripts/reset_password.sh your_new_secure_password
  ```
