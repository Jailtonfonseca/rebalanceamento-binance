"""The central orchestrator for the portfolio rebalancing process.

This module defines the `RebalanceExecutor` class, which ties together all the
services (configuration, exchange clients, database) to perform the full
rebalancing flow. It ensures that rebalancing operations are executed
atomically and logs the entire process.
"""

import asyncio
import uuid
import logging
from typing import List

from sqlalchemy.orm import Session

from app.services.config_manager import ConfigManager
from app.services.binance_client import BinanceClient
from app.services.cmc_client import CoinMarketCapClient
from app.services.rebalance_engine import RebalanceEngine
from app.services.models import ProposedTrade, RebalanceResult
from app.db.models import RebalanceRun
from app.utils.helpers import format_quantity_for_api

logger = logging.getLogger(__name__)


class RebalanceExecutor:
    """Orchestrates the rebalancing process.

    This class coordinates fetching data from various sources, running the
    rebalancing logic to generate a trade plan, executing the plan, and
    saving the results. It uses a lock to prevent concurrent rebalancing runs.

    Attributes:
        config: The application settings.
        binance_client: The client for interacting with the Binance API.
        cmc_client: The client for interacting with the CoinMarketCap API.
        engine: The engine that calculates the rebalancing trades.
        db: The SQLAlchemy database session.
    """

    _lock = asyncio.Lock()

    def __init__(
        self,
        config_manager: ConfigManager,
        binance_client: BinanceClient,
        cmc_client: CoinMarketCapClient,
        rebalance_engine: RebalanceEngine,
        db_session: Session,
    ):
        """Initializes the RebalanceExecutor.

        Args:
            config_manager: The application's configuration manager.
            binance_client: An initialized Binance API client.
            cmc_client: An initialized CoinMarketCap API client.
            rebalance_engine: An initialized rebalancing engine.
            db_session: An active SQLAlchemy database session.
        """
        self.config = config_manager.get_settings()
        self.binance_client = binance_client
        self.cmc_client = cmc_client
        self.engine = rebalance_engine
        self.db = db_session

    async def execute_rebalance_flow(
        self, dry_run_override: bool = None
    ) -> RebalanceResult:
        """Executes the full rebalancing flow.

        This method orchestrates the entire process:
        1. Fetches market data and account balances.
        2. Runs the rebalancing engine to calculate a trade plan.
        3. Executes or simulates the trades based on the plan.
        4. Saves the results of the run to the database.

        A lock prevents this method from running concurrently.

        Args:
            dry_run_override: If specified, this value overrides the dry_run
                              setting from the configuration.

        Returns:
            A RebalanceResult object summarizing the outcome of the run.

        Raises:
            RuntimeError: If a rebalancing process is already in progress.
        """
        if self._lock.locked():
            logger.warning("A rebalancing process is already running.")
            raise RuntimeError("Processo de rebalanceamento já está em andamento.")

        async with self._lock:
            run_id = str(uuid.uuid4())
            is_dry_run = (
                self.config.dry_run if dry_run_override is None else dry_run_override
            )
            logger.info(
                f"--- Starting Rebalance Run (ID: {run_id}, Dry Run: {is_dry_run}) ---"
            )

            total_value_before: float | None = None

            try:
                # 1. Fetch all necessary data
                balances = await self.binance_client.get_account_balances()
                all_prices = await self.binance_client.get_all_prices()

                total_value_before = self._calculate_portfolio_value(
                    balances, all_prices
                )

                # Create a list of all potential symbols we might need info for
                potential_symbols = {
                    f"{asset}{self.config.base_pair}"
                    for asset in self.config.allocations.keys()
                }
                exchange_info = await self.binance_client.get_exchange_info(
                    list(potential_symbols)
                )

                cmc_symbols = await self.cmc_client.get_latest_listings(
                    limit=self.config.max_cmc_rank
                )

                # 2. Run the engine to get the trade plan
                engine_result = self.engine.run(
                    balances=balances,
                    prices=all_prices,
                    exchange_info=exchange_info,
                    target_allocations=self.config.allocations,
                    eligible_cmc_symbols=cmc_symbols,
                    base_pair=self.config.base_pair,
                    min_trade_value_usd=self.config.min_trade_value_usd,
                    trade_fee_pct=self.config.trade_fee_pct,
                )

                projected_balances = engine_result["projected_balances"]
                total_value_after = self._calculate_total_from_projected(
                    projected_balances
                )

                proposed_trades = engine_result["proposed_trades"]
                if not proposed_trades:
                    message = (
                        "O portfólio já está balanceado. Nenhuma transação necessária."
                    )
                    result = RebalanceResult(
                        run_id=run_id,
                        status="SUCCESS",
                        message=message,
                        trades=[],
                        projected_balances=projected_balances,
                    )
                    self._save_result(
                        result,
                        is_dry_run,
                        total_value_usd_before=total_value_before,
                        total_value_usd_after=total_value_after,
                    )
                    return result

                # 3. Execute or simulate trades
                result = await self._execute_plan(proposed_trades, run_id, is_dry_run)

                # 4. Add final data to result and save to the database
                result.projected_balances = projected_balances
                result.total_fees_usd = engine_result["total_fees_usd"]
                self._save_result(
                    result,
                    is_dry_run,
                    total_value_usd_before=total_value_before,
                    total_value_usd_after=total_value_after,
                )

                logger.info(f"--- Finished Rebalance Run (ID: {run_id}) ---")
                return result

            except Exception as e:
                logger.error(
                    f"Unhandled exception during rebalance flow: {e}", exc_info=True
                )
                result = RebalanceResult(
                    run_id=run_id, status="FAILED", message=str(e), trades=[]
                )
                self._save_result(
                    result,
                    is_dry_run=True,
                    total_value_usd_before=total_value_before,
                    total_value_usd_after=None,
                )  # Always save failed runs as "dry"
                raise

    async def _execute_plan(
        self, trades: List[ProposedTrade], run_id: str, is_dry_run: bool
    ) -> RebalanceResult:
        """Executes or simulates a list of proposed trades.

        Sells are processed before buys to free up capital. If `is_dry_run` is
        True, trades are only logged. Otherwise, they are executed via the
        Binance client.

        Args:
            trades: A list of ProposedTrade objects to execute.
            run_id: The unique ID for the current rebalancing run.
            is_dry_run: A boolean indicating whether to execute real trades.

        Returns:
            A RebalanceResult object detailing the executed trades and any errors.
        """
        executed_trades: List[ProposedTrade] = []
        errors: List[str] = []

        # Process sells first
        sells = [t for t in trades if t.side == "SELL"]
        buys = [t for t in trades if t.side == "BUY"]

        for trade in sells + buys:
            try:
                if not is_dry_run:
                    logger.info(
                        f"EXECUTE: {trade.side} {trade.quantity} {trade.symbol}"
                    )
                    # Format the quantity to a plain string before sending to the API
                    quantity_str = format_quantity_for_api(trade.quantity)
                    await self.binance_client.create_order(
                        symbol=trade.symbol,
                        side=trade.side,
                        quantity=quantity_str,
                        test=False,  # This is a real order
                    )
                else:
                    logger.info(
                        f"DRY RUN: {trade.side} {trade.quantity} {trade.symbol}"
                    )

                executed_trades.append(trade)

            except Exception as e:
                error_msg = f"Falha ao executar {trade.side} {trade.symbol}: {e}"
                logger.error(error_msg, exc_info=True)
                errors.append(error_msg)

        # Determine final status
        status = "DRY_RUN" if is_dry_run else "SUCCESS"
        message = f"Simulação concluída. {len(executed_trades)} transações simuladas."
        if not is_dry_run:
            if errors:
                status = "PARTIAL_SUCCESS"
                message = (
                    f"Rebalanceamento parcialmente concluído com {len(errors)} erros."
                )
            else:
                message = f"Rebalanceamento concluído com sucesso. {len(executed_trades)} transações executadas."

        return RebalanceResult(
            run_id=run_id,
            status=status,
            message=message,
            trades=executed_trades,
            errors=errors,
        )

    def _calculate_portfolio_value(
        self, balances: dict[str, float], prices: dict[str, float]
    ) -> float | None:
        """Calculates the total portfolio value using the provided balances."""

        if not balances:
            return None

        total_value = 0.0
        for asset, quantity in balances.items():
            if asset == self.config.base_pair:
                total_value += quantity
                continue

            symbol = f"{asset}{self.config.base_pair}"
            price = prices.get(symbol)
            if price is None:
                logger.debug(
                    "Skipping asset %s in total calculation; missing price for %s",
                    asset,
                    symbol,
                )
                continue
            total_value += quantity * price

        return total_value

    @staticmethod
    def _calculate_total_from_projected(
        projected_balances: dict | None,
    ) -> float | None:
        """Calculates the total USD value from projected balances."""

        if projected_balances is None:
            return None

        if not projected_balances:
            return 0.0

        total_value = 0.0
        for details in projected_balances.values():
            if not isinstance(details, dict):
                continue
            value = details.get("value_usd")
            if value is None:
                continue
            total_value += float(value)

        return total_value

    def _save_result(
        self,
        result: RebalanceResult,
        is_dry_run: bool,
        *,
        total_value_usd_before: float | None = None,
        total_value_usd_after: float | None = None,
    ):
        """Saves the result of a rebalancing run to the database.

        Args:
            result: The RebalanceResult object from the execution.
            is_dry_run: A boolean indicating if the run was a simulation.
            total_value_usd_before: Total portfolio value before the run, if known.
            total_value_usd_after: Total projected portfolio value after the run, if known.
        """
        db_run = RebalanceRun(
            run_id=result.run_id,
            timestamp=result.timestamp,
            status=result.status,
            is_dry_run=is_dry_run,
            summary_message=result.message,
            trades_executed=[t.model_dump() for t in result.trades],
            errors=result.errors,
            total_fees_usd=result.total_fees_usd,
            projected_balances=result.projected_balances,
            total_value_usd_before=total_value_usd_before,
            total_value_usd_after=total_value_usd_after,
        )
        self.db.add(db_run)
        self.db.commit()
        self.db.refresh(db_run)
        logger.info(f"Saved rebalance run {result.run_id} to database.")
