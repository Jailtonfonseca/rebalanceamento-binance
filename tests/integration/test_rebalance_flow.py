from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, RebalanceRun
from app.services.binance_client import BinanceClient
from app.services.cmc_client import CoinMarketCapClient
from app.services.config_manager import (
    ConfigManager,
    AppSettings,
    BinanceSettings,
    CMCSettings,
)
from app.api.v1_rebalance import run_rebalance_manually
from app.api.v1_history import get_portfolio_statistics

# --- Test Database Setup ---
DATABASE_URL = "sqlite:///:memory:"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Pytest Fixtures ---


@pytest.fixture(scope="function")
def db_session():
    """Create a new database session for each test function."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def mock_config_manager():
    """Fixture to provide a consistent, mocked config manager."""
    mock_settings = AppSettings(
        binance=BinanceSettings(
            api_key="test",
            secret_key="test",
            api_key_encrypted=b"gAAAAA...",
            secret_key_encrypted=b"gAAAAA...",
        ),
        cmc=CMCSettings(api_key="test", api_key_encrypted=b"gAAAAA..."),
        allocations={"BTC": 60.0, "ETH": 40.0},
        base_pair="USDT",
        max_cmc_rank=100,
        dry_run=True,
        min_trade_value_usd=10.0,
        trade_fee_pct=0.1,
    )

    class MockConfigManager(ConfigManager):
        def get_settings(self) -> AppSettings:
            return mock_settings

        def decrypt(self, val):
            return "decrypted_key"

    return MockConfigManager()


@pytest.mark.anyio
async def test_rebalance_flow_direct_call(db_session, monkeypatch, mock_config_manager):
    """
    Tests the full rebalancing flow by calling the endpoint function directly.
    """

    # --- Mock External Services ---
    async def mock_get_balances(*args, **kwargs):
        # Current: BTC 72k (72%), ETH 18k (18%), USDT 10k (10%) -> Total 100k
        return {"BTC": 1.2, "ETH": 6.0, "USDT": 10000.0}

    async def mock_get_prices(*args, **kwargs):
        return {"BTCUSDT": 60000.0, "ETHUSDT": 3000.0}

    async def mock_get_exchange_info(*args, **kwargs):
        return {
            "BTCUSDT": {
                "symbol": "BTCUSDT",
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": "0.00001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.0"},
                ],
            },
            "ETHUSDT": {
                "symbol": "ETHUSDT",
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": "0.0001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.0"},
                ],
            },
        }

    async def mock_get_cmc_listings(*args, **kwargs):
        return {"BTC", "ETH", "USDT"}

    monkeypatch.setattr(BinanceClient, "get_account_balances", mock_get_balances)
    monkeypatch.setattr(BinanceClient, "get_all_prices", mock_get_prices)
    monkeypatch.setattr(BinanceClient, "get_exchange_info", mock_get_exchange_info)
    monkeypatch.setattr(
        CoinMarketCapClient, "get_latest_listings", mock_get_cmc_listings
    )

    # --- Call the function directly ---
    result = await run_rebalance_manually(
        dry=True, db=db_session, config_manager=mock_config_manager
    )

    # --- Assertions ---
    # Target: BTC 60%, ETH 40%.
    # Sell BTC: 12% of 100k = 12k. Buy ETH: 22% of 100k = 22k.
    assert result.status == "DRY_RUN"
    assert "Simulação concluída" in result.message
    assert len(result.trades) == 2

    sell_trade = next((t for t in result.trades if t.side == "SELL"), None)
    buy_trade = next((t for t in result.trades if t.side == "BUY"), None)

    assert sell_trade is not None
    assert sell_trade.asset == "BTC"
    # With the new logic, rebalancing is based on the eligible asset value ($90k), not total portfolio value ($100k)
    # Target values: BTC=54k, ETH=36k. Current: BTC=72k, ETH=18k.
    # Deltas: Sell 18k BTC, Buy 18k ETH.
    assert sell_trade.estimated_value_usd == pytest.approx(18000)
    assert sell_trade.fee_cost_usd == pytest.approx(18.0)

    assert buy_trade is not None
    assert buy_trade.asset == "ETH"
    assert buy_trade.estimated_value_usd == pytest.approx(18000)
    assert buy_trade.fee_cost_usd == pytest.approx(18.0)

    # Assert totals and projected balances
    assert result.total_fees_usd == pytest.approx(36.0)
    assert result.projected_balances is not None
    # Initial: 1.2 BTC. Sell 18k/60k = 0.3 BTC. Final: 0.9 BTC
    assert result.projected_balances["BTC"]["quantity"] == pytest.approx(0.9)
    # Initial: 6 ETH. Buy 18k/3k = 6 ETH. After fee: 6 * (1-0.001) = 5.994. Final: 11.994 ETH
    assert result.projected_balances["ETH"]["quantity"] == pytest.approx(11.994)
    # Initial: 10k USDT. Buy 18k ETH -> -18k. Sell 18k BTC -> +18k*(1-0.001)=17982. Final: 9982
    assert result.projected_balances["USDT"]["quantity"] == pytest.approx(9982)


    # Assert database write
    db_run = db_session.query(RebalanceRun).filter_by(run_id=result.run_id).first()
    assert db_run is not None
    assert db_run.status == "DRY_RUN"
    assert db_run.is_dry_run is True
    assert len(db_run.trades_executed) == 2
    assert db_run.trades_executed[0]["asset"] == "BTC"
    assert db_run.total_fees_usd == pytest.approx(36.0)
    assert db_run.total_value_usd_before == pytest.approx(100000.0)
    assert db_run.total_value_usd_after == pytest.approx(99964.0)
    assert db_run.projected_balances["BTC"]["quantity"] == pytest.approx(0.9)


@pytest.mark.anyio
async def test_get_portfolio_statistics(db_session):
    """Ensure the portfolio statistics endpoint aggregates data correctly."""

    run1 = RebalanceRun(
        run_id="run-1",
        timestamp=datetime(2024, 1, 1, 12, 0, 0),
        status="SUCCESS",
        is_dry_run=False,
        summary_message="Primeira execução",
        trades_executed=[],
        errors=[],
        total_fees_usd=0.0,
        projected_balances={
            "BTC": {"quantity": 1.0, "value_usd": 50000.0},
            "USDT": {"quantity": 1000.0, "value_usd": 1000.0},
        },
        total_value_usd_before=51000.0,
        total_value_usd_after=51000.0,
    )

    run2 = RebalanceRun(
        run_id="run-2",
        timestamp=datetime(2024, 1, 2, 12, 0, 0),
        status="SUCCESS",
        is_dry_run=False,
        summary_message="Segunda execução",
        trades_executed=[],
        errors=[],
        total_fees_usd=0.0,
        projected_balances={
            "BTC": {"quantity": 0.8, "value_usd": 40000.0},
            "ETH": {"quantity": 5.0, "value_usd": 15000.0},
            "USDT": {"quantity": 2000.0, "value_usd": 2000.0},
        },
        total_value_usd_before=51000.0,
        total_value_usd_after=None,  # Force fallback to sum projected balances
    )

    db_session.add_all([run1, run2])
    db_session.commit()

    stats = await get_portfolio_statistics(db=db_session)

    assert "portfolio" in stats and "assets" in stats
    assert len(stats["portfolio"]) == 2
    assert stats["portfolio"][0]["total_value_usd"] == pytest.approx(51000.0)
    assert stats["portfolio"][1]["total_value_usd"] == pytest.approx(57000.0)
    assert stats["portfolio"][0]["timestamp"].endswith("Z")

    btc_history = stats["assets"].get("BTC")
    assert btc_history is not None and len(btc_history) == 2
    assert btc_history[0]["value_usd"] == pytest.approx(50000.0)
    assert btc_history[1]["quantity"] == pytest.approx(0.8)

    eth_history = stats["assets"].get("ETH")
    assert eth_history is not None and len(eth_history) == 1
    assert eth_history[0]["value_usd"] == pytest.approx(15000.0)

    usdt_history = stats["assets"].get("USDT")
    assert usdt_history is not None and len(usdt_history) == 2
    assert usdt_history[1]["value_usd"] == pytest.approx(2000.0)
