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

    assert len(trades) == 1  # Sell BTC. Buy ETH skipped due to insufficient funds.

    sell_trade = next(t for t in trades if t.side == "SELL")
    buy_trade = next((t for t in trades if t.side == "BUY"), None)

    # Based on TOTAL value of 100k:
    # Sell BTC: current 75k, target 60k -> Sell 15k
    # Buy ETH: current 20k, target 30k -> Buy 10k
    assert sell_trade.asset == "BTC"
    assert sell_trade.estimated_value_base == pytest.approx(15000, rel=1e-3)
    assert sell_trade.estimated_value_usd == pytest.approx(15000, rel=1e-3)
    assert sell_trade.quantity == pytest.approx(15000 / 50000, rel=1e-3)

    assert buy_trade is None


def test_trade_below_min_value_is_ignored(rebalance_engine, mock_data):
    """Test that a trade with a value below min_trade_value_usd is ignored."""
    # Based on total value: Current allocs: BTC=75%, ETH=20%. Set targets very close.
    target_allocations = {"BTC": 75.05, "ETH": 20.0, "USDT": 4.95}
    mock_data["min_trade_value_usd"] = 100.0  # Set a high min trade value

    # Delta for BTC is 0.05% of 100k = $50, which is below the $100 min trade value.
    # All other deltas are smaller. No trades should be proposed.

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

    # No trades should be proposed. The BTC trade is below min notional,
    # and the ETH trade is skipped due to insufficient funds.
    assert len(trades) == 0


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
    # Target value is 10% of total value (110k) = 11k
    assert buy_bnb_trade.estimated_value_base == pytest.approx(11000, rel=1e-3)
    assert buy_bnb_trade.estimated_value_usd == pytest.approx(11000, rel=1e-3)
    assert buy_bnb_trade.quantity == pytest.approx(11000 / 300.0, rel=1e-3)


def test_projected_balances_with_buy_fee(rebalance_engine, mock_data):
    """
    Test that projected balances are calculated correctly for a BUY trade,
    ensuring the fee is paid from the base currency.
    """
    balances = {"BTC": 1.0, "USDT": 50000}  # BTC=50k, USDT=50k, Total=100k
    target_allocations = {"BTC": 80.0, "USDT": 20.0}  # Target: BTC=80k, USDT=20k
    trade_fee_pct = 0.1  # Buy $30k worth of BTC

    result = rebalance_engine.run(
        balances=balances,
        prices=mock_data["prices"],
        exchange_info=mock_data["exchange_info"],
        target_allocations=target_allocations,
        eligible_cmc_symbols=mock_data["eligible_cmc_symbols"],
        base_pair=mock_data["base_pair"],
        min_trade_value_usd=mock_data["min_trade_value_usd"],
        trade_fee_pct=trade_fee_pct,
    )

    projected = result["projected_balances"]
    buy_trade = result["proposed_trades"][0]

    # Sanity check the trade proposal
    assert buy_trade.asset == "BTC"
    assert buy_trade.side == "BUY"
    assert buy_trade.estimated_value_base == pytest.approx(30000, rel=1e-3)
    assert buy_trade.quantity == pytest.approx(0.6, rel=1e-3)

    # Verify projected balances (the CORRECT calculation)
    # Initial BTC was 1.0, we bought 0.6. Should be 1.6.
    assert projected["BTC"]["quantity"] == pytest.approx(1.0 + 0.6)

    # Initial USDT was 50000. We spent 30000 on BTC and 0.1% fee on that.
    # Fee = 30000 * 0.001 = 30 USDT. Total cost = 30030 USDT.
    # Remaining USDT = 50000 - 30030 = 19970 USDT.
    assert projected["USDT"]["quantity"] == pytest.approx(19970)
