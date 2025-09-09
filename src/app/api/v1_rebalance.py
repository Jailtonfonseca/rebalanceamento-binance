"""API endpoint for triggering the rebalancing process.

This module provides the route to manually initiate a portfolio
rebalancing run.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import get_db
from app.services.config_manager import ConfigManager, get_config_manager
from app.services.binance_client import BinanceClient
from app.services.cmc_client import CoinMarketCapClient
from app.services.rebalance_engine import RebalanceEngine
from app.services.executor import RebalanceExecutor
from app.services.models import RebalanceResult

router = APIRouter(tags=["Rebalancing"])


@router.post("/rebalance/run", response_model=RebalanceResult)
async def run_rebalance_manually(
    dry: bool = Query(
        None, description="Override the saved dry-run setting for this run."
    ),
    db: Session = Depends(get_db),
    config_manager: ConfigManager = Depends(get_config_manager),
):
    """Manually triggers a rebalancing run.

    This endpoint initializes all the necessary services and invokes the
    `RebalanceExecutor` to perform the entire rebalancing flow. It allows
    overriding the dry-run setting for a one-off execution.

    Args:
        dry: An optional query parameter to override the dry-run setting.
        db: The database session, injected by FastAPI.
        config_manager: The configuration manager, injected by FastAPI.

    Returns:
        A `RebalanceResult` object detailing the outcome of the run.

    Raises:
        HTTPException: If API keys are not configured, if a run is already
                       in progress, or if an unexpected error occurs.
    """
    settings = config_manager.get_settings()

    # Decrypt keys to initialize clients
    binance_api_key = config_manager.decrypt(settings.binance.api_key_encrypted)
    binance_secret_key = config_manager.decrypt(settings.binance.secret_key_encrypted)
    cmc_api_key = config_manager.decrypt(settings.cmc.api_key_encrypted)

    if not all([binance_api_key, binance_secret_key, cmc_api_key]):
        raise HTTPException(
            status_code=400, detail="As chaves de API não estão totalmente configuradas."
        )

    # Initialize all services needed for the flow
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

    try:
        result = await executor.execute_rebalance_flow(dry_run_override=dry)
        return result
    except RuntimeError as e:
        # This typically happens if the lock is already acquired
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        # Catch other potential errors during setup
        raise HTTPException(
            status_code=500, detail=f"Ocorreu um erro inesperado: {e}"
        )
