"""Manages the scheduled execution of the rebalancing process.

This module uses APScheduler to run the rebalancing job at a configurable
interval. It defines the job itself and provides a function to configure
and start the scheduler based on the application's settings.
"""

import logging
import uuid
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.models import SessionLocal, RebalanceRun
from app.services.config_manager import get_config_manager, AppSettings, DecryptionError
from app.services.binance_client import BinanceClient
from app.services.cmc_client import CoinMarketCapClient
from app.services.rebalance_engine import RebalanceEngine
from app.services.executor import RebalanceExecutor

logger = logging.getLogger(__name__)

# Initialize the scheduler
scheduler = AsyncIOScheduler(timezone="UTC")


async def scheduled_rebalance_job():
    """The core function executed by the scheduler.

    This job performs the following actions:
    1. Initializes all necessary services and clients within its own scope.
    2. Checks if the conditions for a periodic run are met (strategy is
       'periodic' and not in dry run mode).
    3. Creates a new database session for the job.
    4. Initializes and runs the `RebalanceExecutor` to perform the flow.
    5. Handles any exceptions and ensures the database session is closed.
    """
    logger.info("Scheduler triggered: Starting periodic rebalance job...")

    # We need to create our own instances of services for this background job.
    config_manager = get_config_manager()
    settings = config_manager.get_settings()

    # Only run the periodic job when strategy is set to 'periodic'.
    if settings.strategy != "periodic":
        logger.info(
            "Scheduler job skipped: Strategy is not 'periodic'."
        )
        return

    # Create a new DB session for this job
    db = SessionLocal()

    try:
        # Decrypt keys to initialize clients
        binance_api_key = config_manager.decrypt(settings.binance.api_key_encrypted)
        binance_secret_key = config_manager.decrypt(
            settings.binance.secret_key_encrypted
        )
        cmc_api_key = config_manager.decrypt(settings.cmc.api_key_encrypted)

        if not all([binance_api_key, binance_secret_key, cmc_api_key]):
            logger.error("Scheduler job proceeding but API keys are not fully configured. The run may fail and be recorded as FAILED.")

        # Initialize all services
        binance_client = BinanceClient(
            api_key=binance_api_key, secret_key=binance_secret_key
        )
        cmc_client = CoinMarketCapClient(api_key=cmc_api_key)
        rebalance_engine = RebalanceEngine()

        executor = RebalanceExecutor(
            config_manager=config_manager,
            binance_client=binance_client,
            cmc_client=cmc_client,
            rebalance_engine=rebalance_engine,
            db_session=db,
        )

        await executor.execute_rebalance_flow(dry_run_override=settings.dry_run)

    except DecryptionError as e:
        # Record decryption-related failures into history so the user can see attempts
        run_id = str(uuid.uuid4())
        db.add(
            RebalanceRun(
                run_id=run_id,
                status="FAILED",
                is_dry_run=True,
                summary_message="Falha ao descriptografar chaves. Verifique a MASTER_KEY e regrave as chaves.",
                trades_executed=[],
                errors=[str(e)],
                total_fees_usd=0.0,
                projected_balances=None,
            )
        )
        db.commit()
        logger.error(
            f"Decryption error during scheduled job; recorded FAILED run_id={run_id}: {e}",
            exc_info=True,
        )
    except Exception as e:
        logger.error(
            f"An error occurred during the scheduled rebalance job: {e}", exc_info=True
        )
    finally:
        db.close()
        logger.info("Scheduler job finished.")


def setup_scheduler(settings: AppSettings):
    """Configures and starts the scheduler.

    This function adds the `scheduled_rebalance_job` to the scheduler with
    the interval specified in the application settings. If the scheduler is
    not already running, it starts it.

    Args:
        settings: The application settings object containing scheduler config.
    """
    if scheduler.get_job("periodic_rebalance"):
        scheduler.remove_job("periodic_rebalance")

    scheduler.add_job(
        scheduled_rebalance_job,
        "interval",
        hours=settings.periodic_hours,
        id="periodic_rebalance",
        replace_existing=True,
    )

    if not scheduler.running:
        scheduler.start()
        logger.info(
            f"Scheduler started. Job will run every {settings.periodic_hours} hours."
        )
