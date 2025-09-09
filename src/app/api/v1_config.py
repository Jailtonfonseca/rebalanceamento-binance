"""API endpoints for managing the application's configuration.

This module provides the routes for viewing, updating, and testing the
application's settings, including API keys and rebalancing strategies.
It uses Pydantic models to ensure that no sensitive data is exposed.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import bcrypt

from app.services.config_manager import (
    AppSettings,
    ConfigManager,
    get_config_manager,
    get_settings,
)

# Placeholder for client implementations
from app.services.binance_client import BinanceClient
from app.services.cmc_client import CoinMarketCapClient

router = APIRouter()

# --- Response Models to avoid leaking secrets ---


class PublicBinanceSettings(BaseModel):
    """A Pydantic model for publicly exposing Binance settings status."""
    api_key_set: bool
    secret_key_set: bool


class PublicCMCSettings(BaseModel):
    """A Pydantic model for publicly exposing CoinMarketCap settings status."""
    api_key_set: bool


class PublicAppSettings(BaseModel):
    """A version of AppSettings that is safe to return to the client.

    This model redacts all secret and encrypted fields, only indicating
    whether they have been set or not.
    """

    admin_user: str
    binance: PublicBinanceSettings
    cmc: PublicCMCSettings
    max_cmc_rank: int
    strategy: str
    periodic_hours: int
    threshold_pct: float
    allocations: dict[str, float]
    base_pair: str
    dry_run: bool
    min_trade_value_usd: float


# --- Endpoints ---


@router.get("/config", response_model=PublicAppSettings, tags=["Configuration"])
async def get_public_config(settings: AppSettings = Depends(get_settings)):
    """Gets the current application configuration.

    This endpoint returns the application settings in a "public" format,
    meaning any sensitive fields like API keys are redacted. It only shows
    whether keys have been set or not.

    Args:
        settings: The application settings, injected by FastAPI.

    Returns:
        A PublicAppSettings object with the safe-to-view configuration.
    """
    return PublicAppSettings(
        admin_user=settings.admin_user,
        binance=PublicBinanceSettings(
            api_key_set=bool(settings.binance.api_key_encrypted),
            secret_key_set=bool(settings.binance.secret_key_encrypted),
        ),
        cmc=PublicCMCSettings(api_key_set=bool(settings.cmc.api_key_encrypted)),
        max_cmc_rank=settings.max_cmc_rank,
        strategy=settings.strategy,
        periodic_hours=settings.periodic_hours,
        threshold_pct=settings.threshold_pct,
        allocations=settings.allocations,
        base_pair=settings.base_pair,
        dry_run=settings.dry_run,
        min_trade_value_usd=settings.min_trade_value_usd,
    )


@router.post("/config", status_code=status.HTTP_204_NO_CONTENT, tags=["Configuration"])
async def update_config(
    request: Request,
    config_manager: ConfigManager = Depends(get_config_manager),
):
    """Updates and saves the application configuration.

    This endpoint receives form data, parses it, updates the settings object,
    and then saves it using the ConfigManager. It handles various data types,
    including API keys, passwords, and the asset allocation dictionary.

    Args:
        request: The incoming FastAPI request, containing form data.
        config_manager: The configuration manager, injected by FastAPI.

    Raises:
        HTTPException: If the provided allocations do not sum to 100.
    """
    form_data = await request.form()
    current_settings = config_manager.get_settings().copy(deep=True)

    # Simple fields
    current_settings.dry_run = form_data.get("dry_run") == "true"
    current_settings.base_pair = form_data.get(
        "base_pair", current_settings.base_pair
    ).upper()
    current_settings.max_cmc_rank = int(
        form_data.get("max_cmc_rank", current_settings.max_cmc_rank)
    )
    current_settings.strategy = form_data.get("strategy", current_settings.strategy)
    current_settings.periodic_hours = int(
        form_data.get("periodic_hours", current_settings.periodic_hours)
    )
    current_settings.threshold_pct = float(
        form_data.get("threshold_pct", current_settings.threshold_pct)
    )
    current_settings.min_trade_value_usd = float(
        form_data.get("min_trade_value_usd", current_settings.min_trade_value_usd)
    )

    # API Keys (only update if a new value is provided)
    if form_data.get("binance_api_key"):
        current_settings.binance.api_key = form_data.get("binance_api_key")
    if form_data.get("binance_secret_key"):
        current_settings.binance.secret_key = form_data.get("binance_secret_key")
    if form_data.get("cmc_api_key"):
        current_settings.cmc.api_key = form_data.get("cmc_api_key")

    # Password
    new_password = form_data.get("admin_password")
    if new_password:
        hashed_password = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt())
        current_settings.password_hash = hashed_password

    # Allocations (this is a bit tricky from a flat form)
    allocations = {}
    for key, value in form_data.items():
        if key.startswith("allocations[") and key.endswith("]"):
            symbol = key.split("[")[1].split("]")[0]
            if symbol and value:
                try:
                    allocations[symbol.upper()] = float(value)
                except (ValueError, TypeError):
                    pass  # Ignore invalid values

    if allocations:
        # Validate that allocations sum to 100
        if round(sum(allocations.values())) != 100:
            raise HTTPException(
                status_code=400, detail="Allocation percentages must sum to 100."
            )
        current_settings.allocations = allocations

    config_manager.save_settings(current_settings)
    return


@router.post("/config/test-keys", tags=["Configuration"])
async def test_api_keys(config_manager: ConfigManager = Depends(get_config_manager)):
    """Tests the configured API keys for Binance and CoinMarketCap.

    This endpoint attempts to connect to both services using the saved API
    keys. It returns a summary of whether each connection was successful.

    Args:
        config_manager: The configuration manager, injected by FastAPI.

    Returns:
        A JSON response with the status of each service connection.

    Raises:
        HTTPException: If the connection tests fail or keys are not set.
    """
    settings = config_manager.get_settings()

    # Decrypt keys for testing
    binance_api_key = config_manager.decrypt(settings.binance.api_key_encrypted)
    binance_secret_key = config_manager.decrypt(settings.binance.secret_key_encrypted)
    cmc_api_key = config_manager.decrypt(settings.cmc.api_key_encrypted)

    if not all([binance_api_key, binance_secret_key]):
        raise HTTPException(
            status_code=400,
            detail={"service": "Binance", "error": "API Key or Secret is not set."},
        )

    if not cmc_api_key:
        raise HTTPException(
            status_code=400,
            detail={"service": "CoinMarketCap", "error": "API Key is not set."},
        )

    binance_client = BinanceClient(
        api_key=binance_api_key, secret_key=binance_secret_key
    )
    cmc_client = CoinMarketCapClient(api_key=cmc_api_key)

    results = {}
    try:
        await binance_client.test_connectivity()
        results["binance"] = {
            "status": "success",
            "message": "Successfully connected and fetched account info.",
        }
    except Exception as e:
        results["binance"] = {"status": "error", "message": str(e)}

    try:
        await cmc_client.test_connectivity()
        results["cmc"] = {
            "status": "success",
            "message": "Successfully connected and fetched key info.",
        }
    except Exception as e:
        results["cmc"] = {"status": "error", "message": str(e)}

    # Determine overall status
    if all(r["status"] == "success" for r in results.values()):
        return JSONResponse(content=results)
    else:
        raise HTTPException(status_code=400, detail=results)
