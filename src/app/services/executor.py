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

            try:
                # 1. Fetch all necessary data
                balances = await self.binance_client.get_account_balances()
                all_prices = await self.binance_client.get_all_prices()

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

                proposed_trades = engine_result["proposed_trades"]
                if not proposed_trades:
                    message = "O portfólio já está balanceado. Nenhuma transação necessária."
                    result = RebalanceResult(
                        run_id=run_id, status="SUCCESS", message=message, trades=[],
                        projected_balances=engine_result["projected_balances"]
                    )
                    self._save_result(result, is_dry_run)
                    return result

                # 3. Execute or simulate trades
                result = await self._execute_plan(proposed_trades, run_id, is_dry_run)

                # 4. Add final data to result and save to the database
                result.projected_balances = engine_result["projected_balances"]
                result.total_fees_usd = engine_result["total_fees_usd"]
                self._save_result(result, is_dry_run)

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
                    result, is_dry_run=True
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
                    await self.binance_client.create_order(
                        symbol=trade.symbol,
                        side=trade.side,
                        quantity=trade.quantity,
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
                message = f"Rebalanceamento parcialmente concluído com {len(errors)} erros."
            else:
                message = f"Rebalanceamento concluído com sucesso. {len(executed_trades)} transações executadas."

        return RebalanceResult(
            run_id=run_id,
            status=status,
            message=message,
            trades=executed_trades,
            errors=errors,
        )

    def _save_result(self, result: RebalanceResult, is_dry_run: bool):
        """Saves the result of a rebalancing run to the database.

        Args:
            result: The RebalanceResult object from the execution.
            is_dry_run: A boolean indicating if the run was a simulation.
        """
        db_run = RebalanceRun(
            run_id=result.run_id,
            timestamp=result.timestamp,
            status=result.status,
            is_dry_run=is_dry_run,
            summary_message=result.message,
            trades_executed=[t.dict() for t in result.trades],
            errors=result.errors,
            total_fees_usd=result.total_fees_usd,
            projected_balances=result.projected_balances,
        )
        self.db.add(db_run)
        self.db.commit()
        self.db.refresh(db_run)
        logger.info(f"Saved rebalance run {result.run_id} to database.")
