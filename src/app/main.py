from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import v1_config, v1_rebalance, v1_status, v1_pages, v1_history
from app.services.config_manager import config_manager, AppSettings
import logging
from app.services.scheduler import scheduler, setup_scheduler
from app.db.models import init_db
from app.utils.logging import setup_logging
from prometheus_fastapi_instrumentator import Instrumentator

# Create the FastAPI app
app = FastAPI(
    title="Crypto Rebalancing Bot",
    description="A bot to automatically rebalance a crypto portfolio on Binance.",
    version="1.0.0",
)

# --- Prometheus Metrics ---
Instrumentator().instrument(app).expose(app)

# --- Static files and Templates ---
app.mount("/static", StaticFiles(directory="src/web/static"), name="static")

# --- API Routers ---
app.include_router(v1_config.router, prefix="/api/v1")
app.include_router(v1_rebalance.router, prefix="/api/v1")
app.include_router(v1_status.router, prefix="/api/v1")
app.include_router(v1_history.router, prefix="/api/v1")
# This router serves the HTML pages
app.include_router(v1_pages.router)


# --- Application Lifecycle Hooks ---


@app.on_event("startup")
async def startup_event():
    """
    Actions to perform on application startup.
    - Initialize database connections
    - Start the scheduler
    """
    setup_logging()
    # Ensure data directory and DB tables exist
    config_manager.config_path.parent.mkdir(exist_ok=True)
    init_db()

    # Start the scheduler if the strategy is periodic
    settings: AppSettings = config_manager.get_settings()
    if settings.strategy == "periodic":
        setup_scheduler(settings)
    logging.info("Application startup complete.")


@app.on_event("shutdown")
def shutdown_event():
    """
    Actions to perform on application shutdown.
    - Gracefully shut down the scheduler
    """
    logging.info("Application shutdown...")
    if scheduler.running:
        scheduler.shutdown()
    logging.info("Application shutdown complete.")
