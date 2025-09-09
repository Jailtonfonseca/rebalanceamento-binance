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
        trade_fee_pct: float,
    ) -> dict:
        """Calculates the trades needed to match target allocations.

        This method performs the following steps:
        1. Filters assets to a list of eligible candidates.
        2. Calculates the total portfolio value in the specified base pair.
        3. Determines the difference (delta) between the current and target
           allocation for each asset.
        4. Proposes trades for deltas that exceed the minimum trade value.
        5. Adjusts trade quantities to comply with exchange rules (e.g.,
           step size) and filters out trades below the minimum notional value.
        6. Calculates the estimated fee for each trade.
        7. Simulates the trades to calculate projected final balances.

        Args:
            balances: A dictionary of current asset balances.
            prices: A dictionary of current asset prices against the base pair.
            exchange_info: A dictionary of exchange trading rules and filters.
            target_allocations: A dictionary of target asset allocations.
            eligible_cmc_symbols: A set of symbols that meet the CMC rank criteria.
            base_pair: The base currency for trading (e.g., 'USDT').
            min_trade_value_usd: The minimum value for a trade to be proposed.
            trade_fee_pct: The trading fee percentage.

        Returns:
            A dictionary containing the list of proposed trades, the total
            estimated fees, and the projected final balances.
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
            return {"proposed_trades": [], "total_fees_usd": 0, "projected_balances": {}}

        total_eligible_value = sum(v for k, v in current_portfolio_values.items() if k != base_pair)
        total_portfolio_value = sum(current_portfolio_values.values()) # Includes base pair
        logger.debug(f"Total eligible portfolio value (for rebalancing): ${total_eligible_value:,.2f}")
        logger.debug(f"Total portfolio value (including base pair): ${total_portfolio_value:,.2f}")

        if total_eligible_value == 0:
            logger.warning("Total portfolio value is zero. Nothing to rebalance.")
            return {"proposed_trades": [], "total_fees_usd": 0, "projected_balances": {}}

        # 3. Calculate deltas and generate proposed trades
        proposed_trades: List[ProposedTrade] = []
        for asset in preliminary_assets:
            if asset == base_pair:
                continue

            current_value = current_portfolio_values.get(asset, 0.0)
            current_alloc_pct = (current_value / total_eligible_value) * 100 if total_eligible_value else 0
            target_alloc_pct = target_allocations.get(asset, 0.0)

            delta_pct = target_alloc_pct - current_alloc_pct
            delta_usd = (delta_pct / 100) * total_eligible_value

            if abs(delta_usd) < min_trade_value_usd:
                continue

            symbol = f"{asset}{base_pair}"
            price = prices.get(symbol)
            if not price:
                logger.warning(f"No price found for {symbol}. Skipping asset {asset}.")
                continue

            symbol_info = exchange_info.get(symbol)
            if not symbol_info:
                logger.warning(f"No exchange info for {symbol}. Skipping asset {asset}.")
                continue

            lot_size_filter = next((f for f in symbol_info.get("filters", []) if f["filterType"] == "LOT_SIZE"), None)
            min_notional_filter = next((f for f in symbol_info.get("filters", []) if f["filterType"] in ("MIN_NOTIONAL", "NOTIONAL")), None)

            if not lot_size_filter or not min_notional_filter:
                logger.warning(f"Missing LOT_SIZE or MIN_NOTIONAL filter for {symbol}. Skipping.")
                continue

            step_size = lot_size_filter["stepSize"]
            min_notional_value = float(min_notional_filter["minNotional"])

            quantity_to_trade = abs(delta_usd) / price
            adjusted_quantity = adjust_to_step_size(quantity_to_trade, step_size)
            final_trade_value = adjusted_quantity * price

            if adjusted_quantity <= 0 or final_trade_value < min_notional_value:
                continue

            fee_cost = final_trade_value * (trade_fee_pct / 100)
            side = "BUY" if delta_usd > 0 else "SELL"
            reason = f"Target: {target_alloc_pct:.2f}%, Current: {current_alloc_pct:.2f}%, Delta: {delta_pct:.2f}%"

            proposed_trades.append(
                ProposedTrade(
                    symbol=symbol,
                    asset=asset,
                    side=side,
                    quantity=adjusted_quantity,
                    estimated_value_usd=final_trade_value,
                    reason=reason,
                    fee_cost_usd=fee_cost,
                )
            )
            logger.info(f"Proposing trade: {side} {adjusted_quantity} {asset} for ~${final_trade_value:,.2f} (Fee: ~${fee_cost:,.2f})")

        # 4. Calculate projected balances
        projected_balances = balances.copy()
        total_fees_usd = sum(trade.fee_cost_usd for trade in proposed_trades)

        for trade in proposed_trades:
            asset_qty_change = trade.quantity
            base_qty_change = trade.estimated_value_usd

            if trade.side == "BUY":
                # Assume fee is paid from the received asset (Binance standard)
                projected_balances[trade.asset] = projected_balances.get(trade.asset, 0) + (asset_qty_change * (1 - trade_fee_pct / 100))
                projected_balances[base_pair] -= base_qty_change
            else:  # SELL
                projected_balances[trade.asset] -= asset_qty_change
                # Fee is deducted from the quote asset received
                projected_balances[base_pair] += base_qty_change * (1 - trade_fee_pct / 100)

        # 5. Format projected balances with USD values
        final_projected_balances = {}
        for asset, qty in projected_balances.items():
            price = prices.get(f"{asset}{base_pair}", 1.0) if asset != base_pair else 1.0
            final_projected_balances[asset] = {
                "quantity": qty,
                "value_usd": qty * price
            }


        return {
            "proposed_trades": proposed_trades,
            "total_fees_usd": total_fees_usd,
            "projected_balances": final_projected_balances,
        }
