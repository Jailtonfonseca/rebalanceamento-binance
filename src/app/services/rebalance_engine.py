"""The core engine for calculating portfolio rebalancing trades.

This module provides the `RebalanceEngine`, a stateless class responsible for
taking market data, current balances, and target allocations to produce a list
of proposed trades needed to bring the portfolio back into alignment.
"""
from typing import Dict, List, Set

import logging
from app.services.models import ProposedTrade
from app.utils.helpers import adjust_to_step_size

logger = logging.getLogger(__name__)


class RebalanceEngine:
    """Contains the core logic for calculating rebalancing trades.

    This class is stateless and performs no I/O. Its primary method, `run`,
    is a pure function that calculates the necessary trades based on its inputs.
    """

    def run(
        self,
        balances: Dict[str, float],
        prices: Dict[str, float],
        exchange_info: Dict[str, any],
        target_allocations: Dict[str, float],
        eligible_cmc_symbols: Set[str],
        base_pair: str,
        min_trade_value_usd: float,
    ) -> List[ProposedTrade]:
        """Calculates the trades needed to match target allocations.

        This method performs the following steps:
        1. Filters assets to a list of eligible candidates.
        2. Calculates the total portfolio value in the specified base pair.
        3. Determines the difference (delta) between the current and target
           allocation for each asset.
        4. Proposes trades for deltas that exceed the minimum trade value.
        5. Adjusts trade quantities to comply with exchange rules (e.g.,
           step size) and filters out trades below the minimum notional value.

        Args:
            balances: A dictionary of current asset balances.
            prices: A dictionary of current asset prices against the base pair.
            exchange_info: A dictionary of exchange trading rules and filters.
            target_allocations: A dictionary of target asset allocations.
            eligible_cmc_symbols: A set of symbols that meet the CMC rank criteria.
            base_pair: The base currency for trading (e.g., 'USDT').
            min_trade_value_usd: The minimum value for a trade to be proposed.

        Returns:
            A list of ProposedTrade objects representing the trades to execute.
        """
        logger.info("Starting rebalance calculation engine...")

        # 1. Filter assets that are in wallet, in target allocations, and in CMC list
        wallet_symbols = set(balances.keys())
        target_symbols = set(target_allocations.keys())

        # We consider assets that are either in our target list or already in our wallet
        # and are also ranked high enough in CMC. The base pair is always included.
        preliminary_assets = (wallet_symbols | target_symbols) & eligible_cmc_symbols
        preliminary_assets.add(base_pair)  # Ensure base pair is always considered

        logger.debug(f"Preliminary assets for consideration: {preliminary_assets}")

        # 2. Calculate current portfolio value in the base pair (e.g., USD)
        current_portfolio_values = {}
        for asset in preliminary_assets:
            quantity = balances.get(asset, 0.0)
            if asset == base_pair:
                current_portfolio_values[asset] = quantity
            else:
                symbol = f"{asset}{base_pair}"
                price = prices.get(symbol)
                if price and quantity > 0:
                    current_portfolio_values[asset] = quantity * price

        if not current_portfolio_values:
            logger.warning("No assets with value found to rebalance.")
            return []

        total_eligible_value = sum(current_portfolio_values.values())
        logger.debug(f"Total eligible portfolio value: ${total_eligible_value:,.2f}")

        if total_eligible_value == 0:
            logger.warning("Total portfolio value is zero. Nothing to rebalance.")
            return []

        # 3. Calculate deltas and generate proposed trades
        proposed_trades: List[ProposedTrade] = []
        for asset in preliminary_assets:
            # Don't try to sell the base pair itself
            if asset == base_pair:
                continue

            current_value = current_portfolio_values.get(asset, 0.0)
            current_alloc_pct = (current_value / total_eligible_value) * 100
            target_alloc_pct = target_allocations.get(asset, 0.0)

            delta_pct = target_alloc_pct - current_alloc_pct
            delta_usd = (delta_pct / 100) * total_eligible_value

            # 4. Filter trades that are too small
            if abs(delta_usd) < min_trade_value_usd:
                continue

            symbol = f"{asset}{base_pair}"
            price = prices.get(symbol)
            if not price:
                logger.warning(f"No price found for {symbol}. Skipping asset {asset}.")
                continue

            # 5. Validate against exchange rules (stepSize, minNotional)
            symbol_info = exchange_info.get(symbol)
            if not symbol_info:
                logger.warning(
                    f"No exchange info for {symbol}. Skipping asset {asset}."
                )
                continue

            # Get LOT_SIZE filter for stepSize
            lot_size_filter = next(
                (f for f in symbol_info["filters"] if f["filterType"] == "LOT_SIZE"),
                None,
            )
            if not lot_size_filter:
                logger.warning(f"No LOT_SIZE filter for {symbol}. Skipping.")
                continue
            step_size = lot_size_filter["stepSize"]

            # Get MIN_NOTIONAL filter
            min_notional_filter = next(
                (
                    f
                    for f in symbol_info["filters"]
                    if f["filterType"] == "MIN_NOTIONAL"
                ),
                None,
            )
            if not min_notional_filter:
                # Some pairs have NOTIONAL filter instead
                min_notional_filter = next(
                    (
                        f
                        for f in symbol_info["filters"]
                        if f["filterType"] == "NOTIONAL"
                    ),
                    None,
                )
                if not min_notional_filter:
                    logger.warning(
                        f"No MIN_NOTIONAL or NOTIONAL filter for {symbol}. Skipping."
                    )
                    continue

            min_notional_value = float(min_notional_filter["minNotional"])

            # Calculate and adjust quantity
            quantity_to_trade = abs(delta_usd) / price
            adjusted_quantity = adjust_to_step_size(quantity_to_trade, step_size)

            final_trade_value = adjusted_quantity * price

            if adjusted_quantity <= 0 or final_trade_value < min_notional_value:
                logger.debug(
                    f"Trade for {symbol} discarded. Qty: {adjusted_quantity}, Value: ${final_trade_value:.2f} (Min: ${min_notional_value:.2f})"
                )
                continue

            side = "BUY" if delta_usd > 0 else "SELL"

            reason = (
                f"Target: {target_alloc_pct:.2f}%, "
                f"Current: {current_alloc_pct:.2f}%, "
                f"Delta: {delta_pct:.2f}%"
            )

            proposed_trades.append(
                ProposedTrade(
                    symbol=symbol,
                    asset=asset,
                    side=side,
                    quantity=adjusted_quantity,
                    estimated_value_usd=final_trade_value,
                    reason=reason,
                )
            )
            logger.info(
                f"Proposing trade: {side} {adjusted_quantity} {asset} for ~${final_trade_value:,.2f}"
            )

        return proposed_trades
