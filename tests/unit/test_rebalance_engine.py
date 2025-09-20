import pytest
from app.services.rebalance_engine import RebalanceEngine


@pytest.fixture
def rebalance_engine():
    """Returns an instance of the RebalanceEngine."""
    return RebalanceEngine()


@pytest.fixture
def mock_data():
    """Provides a default set of mock data for tests."""
    return {
        "balances": {
            "BTC": 1.5,  # Worth $75,000
            "ETH": 10,  # Worth $20,000
            "USDT": 5000,  # Worth $5,000
            "XRP": 10000,  # Not in target allocs, should be ignored
        },
        "prices": {
            "BTCUSDT": 50000.0,
            "ETHUSDT": 2000.0,
            "BNBUSDT": 300.0,
        },
        "exchange_info": {
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
            "BNBUSDT": {
                "symbol": "BNBUSDT",
                "filters": [
                    {"filterType": "LOT_SIZE", "stepSize": "0.01"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.0"},
                ],
            },
        },
        "eligible_cmc_symbols": {"BTC", "ETH", "USDT", "BNB", "XRP"},
        "base_pair": "USDT",
        "min_trade_value_usd": 10.0,
    }


def test_simple_rebalance(rebalance_engine, mock_data):
    """
    Test a standard rebalance scenario.
    - BTC is overweight (75% vs 60% target)
    - ETH is underweight (20% vs 30% target)
    - USDT is underweight (5% vs 10% target)
    Total value = 75k + 20k + 5k = 100k
    """
    target_allocations = {"BTC": 60.0, "ETH": 30.0, "USDT": 10.0}

    result = rebalance_engine.run(
        balances=mock_data["balances"],
        prices=mock_data["prices"],
        exchange_info=mock_data["exchange_info"],
        target_allocations=target_allocations,
        eligible_cmc_symbols=mock_data["eligible_cmc_symbols"],
        base_pair=mock_data["base_pair"],
        min_trade_value_usd=mock_data["min_trade_value_usd"],
        trade_fee_pct=0.1,
    )
    trades = result["proposed_trades"]

    assert len(trades) == 2  # Sell BTC, Buy ETH. USDT change handled by others.

    sell_trade = next(t for t in trades if t.side == "SELL")
    buy_trade = next(t for t in trades if t.side == "BUY")

    # Based on eligible value of 95k: Sell 18k BTC, Buy 8.5k ETH
    assert sell_trade.asset == "BTC"
    assert sell_trade.estimated_value_base == pytest.approx(18000, rel=1e-3)
    assert sell_trade.estimated_value_usd == pytest.approx(18000, rel=1e-3)
    assert sell_trade.quantity == pytest.approx(18000 / 50000, rel=1e-3)

    assert buy_trade.asset == "ETH"
    assert buy_trade.estimated_value_base == pytest.approx(8500, rel=1e-3)
    assert buy_trade.estimated_value_usd == pytest.approx(8500, rel=1e-3)
    assert buy_trade.quantity == pytest.approx(8500 / 2000, rel=1e-3)


def test_trade_below_min_value_is_ignored(rebalance_engine, mock_data):
    """Test that a trade with a value below min_trade_value_usd is ignored."""
    # Current allocs: BTC=78.95%, ETH=21.05%. Set targets very close to this.
    target_allocations = {"BTC": 78.9, "ETH": 21.1, "USDT": 0.0}
    mock_data["min_trade_value_usd"] = 100.0  # Set a high min trade value

    # With new logic, delta for BTC is now ~$45, still below the $100 min trade value.

    result = rebalance_engine.run(
        balances=mock_data["balances"],
        prices=mock_data["prices"],
        exchange_info=mock_data["exchange_info"],
        target_allocations=target_allocations,
        eligible_cmc_symbols=mock_data["eligible_cmc_symbols"],
        base_pair=mock_data["base_pair"],
        min_trade_value_usd=mock_data["min_trade_value_usd"],
        trade_fee_pct=0.1,
    )

    assert len(result["proposed_trades"]) == 0


def test_trade_below_min_notional_is_ignored(rebalance_engine, mock_data):
    """Test that a trade is ignored if its final value is below the MIN_NOTIONAL filter."""
    mock_data["exchange_info"]["BTCUSDT"]["filters"][1]["minNotional"] = "20000.0"
    target_allocations = {"BTC": 60.0, "ETH": 30.0, "USDT": 10.0}

    # The proposed BTC trade is for $15k, which is below the new 20k minNotional.

    result = rebalance_engine.run(
        balances=mock_data["balances"],
        prices=mock_data["prices"],
        exchange_info=mock_data["exchange_info"],
        target_allocations=target_allocations,
        eligible_cmc_symbols=mock_data["eligible_cmc_symbols"],
        base_pair=mock_data["base_pair"],
        min_trade_value_usd=mock_data["min_trade_value_usd"],
        trade_fee_pct=0.1,
    )
    trades = result["proposed_trades"]

    # Only the ETH trade should remain
    assert len(trades) == 1
    assert trades[0].asset == "ETH"


def test_asset_not_in_cmc_list_is_ignored(rebalance_engine, mock_data):
    """Test that an asset is ignored if it's not in the eligible CMC list."""
    target_allocations = {"BTC": 60.0, "ETH": 30.0, "USDT": 10.0}
    mock_data["eligible_cmc_symbols"] = {"ETH", "USDT"}  # Remove BTC from CMC list

    result = rebalance_engine.run(
        balances=mock_data["balances"],
        prices=mock_data["prices"],
        exchange_info=mock_data["exchange_info"],
        target_allocations=target_allocations,
        eligible_cmc_symbols=mock_data["eligible_cmc_symbols"],
        base_pair=mock_data["base_pair"],
        min_trade_value_usd=mock_data["min_trade_value_usd"],
        trade_fee_pct=0.1,
    )
    trades = result["proposed_trades"]

    # The engine should not propose selling BTC, even though it's overweight,
    # because it's not in the CMC list. It should still buy ETH.
    assert len(trades) == 1
    assert trades[0].asset == "ETH"


def test_new_asset_to_buy(rebalance_engine, mock_data):
    """Test buying a new asset that is not currently in the wallet."""
    target_allocations = {"BTC": 70.0, "ETH": 20.0, "USDT": 0.0, "BNB": 10.0}
    mock_data["balances"]["USDT"] = 15000  # Increase USDT to have funds
    # Total value = 75k + 20k + 15k = 110k

    result = rebalance_engine.run(
        balances=mock_data["balances"],
        prices=mock_data["prices"],
        exchange_info=mock_data["exchange_info"],
        target_allocations=target_allocations,
        eligible_cmc_symbols=mock_data["eligible_cmc_symbols"],
        base_pair=mock_data["base_pair"],
        min_trade_value_usd=mock_data["min_trade_value_usd"],
        trade_fee_pct=0.1,
    )
    trades = result["proposed_trades"]

    assert len(trades) > 0
    buy_bnb_trade = next((t for t in trades if t.asset == "BNB"), None)
    assert buy_bnb_trade is not None
    assert buy_bnb_trade.side == "BUY"
    # Target value is 10% of eligible value (95k) = 9.5k
    assert buy_bnb_trade.estimated_value_base == pytest.approx(9500, rel=1e-3)
    assert buy_bnb_trade.estimated_value_usd == pytest.approx(9500, rel=1e-3)
    assert buy_bnb_trade.quantity == pytest.approx(9500 / 300.0, rel=1e-3)
