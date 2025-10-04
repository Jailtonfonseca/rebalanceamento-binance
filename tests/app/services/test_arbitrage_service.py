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
    # Simulate a profitable opportunity: 1/50000 * 4000 / (1/0.08) > 1
    # Let's make it more obvious: BTC -> ETH -> USDT -> BTC
    # USDT/BTC: 50000, ETH/USDT: 4000, BTC/ETH: 1/0.08 = 12.5. This is not a triangle.
    # Let's try BTC -> ETH -> USDT -> BTC
    # Path: (BTC, ETH, USDT)
    # Trade 1: BTC -> ETH (ETHBTC)
    # Trade 2: ETH -> USDT (ETHUSDT)
    # Trade 3: USDT -> BTC (BTCUSDT) - we need price of BTC in USDT

    # Let's define a clear profitable path: A->B->C->A
    # Start with 1 A. Buy B. Buy C. Buy A.
    # 1 A -> rate(B/A) B -> rate(B/A) * rate(C/B) C -> rate(B/A) * rate(C/B) * rate(A/C) A
    path = ("BTC", "ETH", "USDT")
    arbitrage_service.prices = {
        "ETHBTC": 0.08,      # 1 BTC = 0.08 ETH
        "ETHUSDT": 4000,    # 1 ETH = 4000 USDT
        "BTCUSDT": 50001,   # 1 BTC = 50001 USDT (This makes it profitable)
    }
    # Calculation: 1 / 0.08 * 1/4000 * 50001 = 1.00002
    # Let's trace it manually
    # 1 BTC -> 1/0.08 ETH -> (1/0.08)*4000 USDT -> (1/0.08)*4000 / 50001 BTC
    # (1/0.08) * 4000 / 50001 = 12.5 * 4000 / 50001 = 50000/50001 < 1. This is a loss.
    # The formula needs to be rate1 * rate2 * rate3.
    # Let's check the implementation:
    # rate1 = prices[f"{b}{a}"] -> ETHBTC
    # rate2 = prices[f"{c}{b}"] -> USDTETH (needs to be defined)
    # rate3 = prices[f"{a}{c}"] -> BTCUSDT

    # Correct path: (BTC, ETH, USDT)
    arbitrage_service.prices = {
        "ETHBTC": 0.08,
        "USDTETH": 1/4000,
        "BTCUSDT": 50001,
    }
    # This is not how Binance lists pairs. Let's use the implementation's logic.
    # The code checks for f"{b}{a}", f"{c}{b}", f"{a}{c}"
    # Path: (A, B, C) -> (BTC, ETH, BNB)
    # 1. B/A -> ETHBTC
    # 2. C/B -> BNBETH
    # 3. A/C -> BTCBNB
    arbitrage_service.prices = {
        "ETHBTC": 12.0,      # rate1
        "BNBETH": 0.15,      # rate2
        "BTCBNB": 0.6,       # rate3 -> 12 * 0.15 * 0.6 = 1.08 (profitable)
    }

    opportunity = arbitrage_service._calculate_profitability(("BTC", "ETH", "BNB"))
    assert opportunity is not None
    assert opportunity["path"] == "BTC -> ETH -> BNB -> BTC"
    assert opportunity["profit_margin_percent"] > 0

def test_calculate_profitability_not_profitable(arbitrage_service):
    """
    Tests the profitability calculation for a non-profitable path.
    """
    arbitrage_service.prices = {
        "ETHBTC": 12.0,
        "BNBETH": 0.15,
        "BTCBNB": 0.5, # 12 * 0.15 * 0.5 = 0.9 (loss)
    }
    opportunity = arbitrage_service._calculate_profitability(("BTC", "ETH", "BNB"))
    assert opportunity is None

@pytest.mark.anyio
async def test_find_opportunities_integration(arbitrage_service):
    """
    An integration-style test for the find_opportunities method.
    """
    with patch.object(arbitrage_service, 'fetch_market_data', new_callable=AsyncMock) as mock_fetch:
        arbitrage_service.prices = {
            # Profitable path
            "ETHBTC": 12.0,
            "BNBETH": 0.15,
            "BTCBNB": 0.6,
            # Unprofitable path
            "ADABTC": 0.00001,
            "XRPADA": 100,
            "BTCXRP": 0.00002,
            # Other symbols to create assets
            "LTCUSDT": 100
        }
        arbitrage_service.symbols = list(arbitrage_service.prices.keys())

        # Mock the asset filtering to use our test assets
        assets_to_check = ["BTC", "ETH", "BNB", "ADA", "XRP"]
        with patch('app.services.arbitrage_service.ArbitrageService._get_triangular_paths',
                   return_value=[("BTC", "ETH", "BNB"), ("BTC", "ADA", "XRP")]) as mock_paths:

            opportunities = await arbitrage_service.find_opportunities()

            mock_fetch.assert_called_once()
            assert len(opportunities) == 1
            assert opportunities[0]["path"] == "BTC -> ETH -> BNB -> BTC"
            assert opportunities[0]["profit_margin_percent"] > 0