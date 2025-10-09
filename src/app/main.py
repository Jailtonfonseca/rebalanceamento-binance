from pathlib import Path
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import logging
from pathlib import Path

from prometheus_fastapi_instrumentator import Instrumentator

from app.api import (
    v1_arbitrage,
    v1_auth,
    v1_config,
    v1_history,
    v1_pages,
    v1_rebalance,
    v1_setup,
    v1_status,
)
from app.db.models import init_db
from app.middleware import (
    AuthenticationMiddleware,
    I18nMiddleware,
    SecurityHeadersMiddleware,
    SetupMiddleware,
)
from app.services.config_manager import AppSettings, config_manager
from app.services.scheduler import scheduler, setup_scheduler
from app.utils.logging import setup_logging
from app.utils.middleware import ErrorHandlingMiddleware, RequestIDMiddleware

# Create the FastAPI app
app = FastAPI(
    title="Crypto Rebalancing Bot",
    description="A bot to automatically rebalance a crypto portfolio on Binance.",
    version="1.1.0",
)

# --- Prometheus Metrics ---
Instrumentator().instrument(app).expose(app)

# --- Middlewares ---
# Middlewares are processed in the reverse order they are added. The first
# middleware added is the outermost layer.
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(I18nMiddleware)
app.add_middleware(AuthenticationMiddleware)
app.add_middleware(SetupMiddleware)

# --- Static files and Templates ---
# Define the path to the static directory relative to this file's location.
# main.py -> app -> src / web / static
STATIC_DIR = Path(__file__).parent.parent / "web" / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# --- API Routers ---
app.include_router(v1_config.router, prefix="/api/v1")
app.include_router(v1_rebalance.router, prefix="/api/v1")
app.include_router(v1_status.router, prefix="/api/v1")
app.include_router(v1_history.router, prefix="/api/v1")
app.include_router(v1_arbitrage.router, prefix="/api/v1")
app.include_router(v1_setup.router, prefix="/api/v1")
app.include_router(v1_auth.router, prefix="/api/v1/auth")
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
