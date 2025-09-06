# Crypto Portfolio Rebalancing Bot

This repository contains a fully-featured, containerized bot to automatically rebalance your cryptocurrency portfolio on Binance based on target allocations and market data from CoinMarketCap.

It provides a simple web interface for configuration, status monitoring, and manual control.

## Features

- **Web UI**: Easy-to-use interface for all configuration, served directly from the container.
- **Flexible Strategies**: Rebalance periodically (e.g., every 24 hours) or based on a deviation threshold.
- **Dry Run Mode**: Simulate rebalancing runs without executing any real trades to see the plan first.
- **Binance Integration**: Connects to your Binance account to read balances, get prices, and execute market orders.
- **CoinMarketCap Integration**: Filters your portfolio against top-ranked assets to avoid rebalancing low-quality or delisted coins.
- **Secure**: API keys are encrypted at rest. The bot never exposes your keys, not even in the UI.
- **Persistent**: All configuration and history are saved to a local `./data` directory, surviving container restarts.
- **Dockerized**: Runs in a single, lightweight Docker container for easy deployment.

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

Before running the application, you need to set up your master encryption key.

Create a file named `.env` in the same directory as `docker-compose.yml`.

If this is your first time running the bot, you can leave the key empty to have one generated for you:
```env
# .env file
MASTER_KEY=
```
The bot will create a `data/secret.key` file. You should then copy the content of this file into the `MASTER_KEY` variable for future runs.

If you already have a key, paste it here:
```env
# .env file
MASTER_KEY=your_super_secret_and_long_encryption_key_here
```

### 2. Build and Run

With Docker running, execute the following command in your terminal:

```bash
docker-compose up --build -d
```
This will build the Docker image and start the container in detached mode.

### 3. Access the UI

Once the container is running, open your web browser and navigate to:

**http://localhost:8080**

The default login credentials are:
- **Username**: `admin`
- **Password**: `admin`

You should change the password immediately via the Configuration page.

---

## Usage

The web interface has three main sections:

- **Dashboard**: Shows the status of the last rebalance run, your current portfolio balances (with their approximate USD value), and allows you to manually trigger a live or dry run.
- **Configuration**: The main settings page. Here you can set your API keys, change your password, define your rebalancing strategy, set your target portfolio allocations, and more.
- **History**: Displays a table of all past rebalancing runs, whether they were successful, and what trades were made.

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
