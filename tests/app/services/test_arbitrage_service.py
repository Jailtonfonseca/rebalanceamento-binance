import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.arbitrage_service import ArbitrageService


@pytest.fixture
def mock_client():
    """Fixture to create a mock httpx.AsyncClient."""
    return AsyncMock()


@pytest.fixture
def arbitrage_service(mock_client):
    """Fixture to create an instance of ArbitrageService with a mock client."""
    return ArbitrageService(client=mock_client)


@pytest.mark.anyio
async def test_fetch_market_data_success(arbitrage_service, mock_client):
    """
    Tests that market data is fetched and processed successfully.
    """
    mock_api_response_data = [
        {"symbol": "BTCUSDT", "price": "50000.0"},
        {"symbol": "ETHUSDT", "price": "4000.0"},
        {"symbol": "ETHBTC", "price": "0.08"},
    ]

    # Create a mock for the response object.
    # The real httpx.Response object has synchronous methods for `raise_for_status()` and `json()`,
    # so we use MagicMock for them to prevent them from being awaitable.
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value=mock_api_response_data)

    # Configure the mock client's get method to return our mock response.
    mock_client.get.return_value = mock_response

    await arbitrage_service.fetch_market_data()

    assert len(arbitrage_service.prices) == 3
    assert arbitrage_service.prices["BTCUSDT"] == 50000.0
    assert "BTCUSDT" in arbitrage_service.symbols


def test_get_triangular_paths(arbitrage_service):
    """
    Tests the generation of triangular paths.
    """
    assets = ["BTC", "ETH", "USDT"]
    paths = arbitrage_service._get_triangular_paths(assets)
    assert len(paths) == 1
    assert ("BTC", "ETH", "USDT") in paths


def test_calculate_profitability_profitable(arbitrage_service):
    """
    Tests the profitability calculation for a profitable path.
    """
    # Real Binance symbols are base+quote. The service must handle both direct
    # and inverse pairs when walking BTC -> ETH -> USDT -> BTC.
    arbitrage_service.prices = {
        "ETHBTC": 0.08,
        "ETHUSDT": 4000.0,
        "BTCUSDT": 49000.0,
    }

    opportunity = arbitrage_service._calculate_profitability(("BTC", "ETH", "USDT"))
    assert opportunity is not None
    assert opportunity["path"] == "BTC -> ETH -> USDT -> BTC"
    assert opportunity["profit_margin_percent"] > 0


def test_calculate_profitability_not_profitable(arbitrage_service):
    """
    Tests the profitability calculation for a non-profitable path.
    """
    arbitrage_service.prices = {
        "ETHBTC": 0.08,
        "ETHUSDT": 4000.0,
        "BTCUSDT": 50000.0,
    }
    opportunity = arbitrage_service._calculate_profitability(("BTC", "ETH", "BNB"))
    assert opportunity is None


@pytest.mark.anyio
async def test_find_opportunities_integration(arbitrage_service):
    """
    An integration-style test for the find_opportunities method.
    """
    with patch.object(
        arbitrage_service, "fetch_market_data", new_callable=AsyncMock
    ) as mock_fetch:
        arbitrage_service.prices = {
            # Profitable path
            "ETHBTC": 0.08,
            "BNBETH": 0.15,
            "BNBBTC": 0.013,
            # Unprofitable path
            "ADABTC": 0.00001,
            "XRPADA": 100,
            "XRPBTC": 0.0000009,
            # Other symbols to create assets
            "LTCUSDT": 100,
        }
        arbitrage_service.symbols = list(arbitrage_service.prices.keys())

        # Mock the path generation to keep this test focused on ranking/filtering.
        with patch(
            "app.services.arbitrage_service.ArbitrageService._get_triangular_paths",
            return_value=[("BTC", "ETH", "BNB"), ("BTC", "ADA", "XRP")],
        ):

            opportunities = await arbitrage_service.find_opportunities()

            mock_fetch.assert_called_once()
            assert len(opportunities) == 1
            assert opportunities[0]["path"] == "BTC -> ETH -> BNB -> BTC"
            assert opportunities[0]["profit_margin_percent"] > 0
