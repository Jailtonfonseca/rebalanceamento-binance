import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.models import SessionLocal
from app.services.config_manager import get_config_manager
from app.services.binance_client import BinanceClient
from app.services.cmc_client import CoinMarketCapClient
from app.services.rebalance_engine import RebalanceEngine
from app.services.executor import RebalanceExecutor

logger = logging.getLogger(__name__)

# Initialize the scheduler
scheduler = AsyncIOScheduler(timezone="UTC")


async def scheduled_rebalance_job():
    """
    This is the function that the scheduler will call periodically.
    It sets up all dependencies and runs the rebalancing flow.
    """
    logger.info("Scheduler triggered: Starting periodic rebalance job...")

    # We need to create our own instances of services for this background job.
    config_manager = get_config_manager()
    settings = config_manager.get_settings()

    # If periodic strategy is not set, or if it's dry run, don't execute
    if settings.strategy != "periodic" or settings.dry_run:
        logger.info(
            "Scheduler job skipped: Strategy is not 'periodic' or dry_run is enabled."
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
            logger.error("Scheduler job failed: API keys are not fully configured.")
            return

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

        await executor.execute_rebalance_flow()

    except Exception as e:
        logger.error(
            f"An error occurred during the scheduled rebalance job: {e}", exc_info=True
        )
    finally:
        db.close()
        logger.info("Scheduler job finished.")


def setup_scheduler(settings):
    """Adds the rebalance job to the scheduler and starts it."""
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
