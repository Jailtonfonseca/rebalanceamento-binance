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
    assert len(result.trades) == 2

    sell_trade = next((t for t in result.trades if t.side == "SELL"), None)
    buy_trade = next((t for t in result.trades if t.side == "BUY"), None)

    assert sell_trade is not None
    assert sell_trade.asset == "BTC"
    assert sell_trade.estimated_value_usd == pytest.approx(12000)

    assert buy_trade is not None
    assert buy_trade.asset == "ETH"
    assert buy_trade.estimated_value_usd == pytest.approx(22000, rel=1e-4)

    # Assert database write
    db_run = db_session.query(RebalanceRun).filter_by(run_id=result.run_id).first()
    assert db_run is not None
    assert db_run.status == "DRY_RUN"
    assert db_run.is_dry_run is True
    assert len(db_run.trades_executed) == 2
    assert db_run.trades_executed[0]["asset"] == "BTC"
