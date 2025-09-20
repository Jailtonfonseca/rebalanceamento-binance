"""API endpoint for fetching the current status of the portfolio.

This module provides the route to get the current asset balances from the
Binance account and their approximate value in USD.
"""

from fastapi import APIRouter, Depends, HTTPException

from app.services.config_manager import get_config_manager, ConfigManager
from app.services.binance_client import BinanceClient, InvalidAPIKeys
from app.utils.pricing import (
    get_asset_base_value,
    get_asset_usd_value,
    resolve_base_to_usd_rate,
)
from app.db.models import SessionLocal
from app.services.scheduler import scheduler
from sqlalchemy import text

router = APIRouter(tags=["Status"])


@router.get("/health", tags=["Status"])
async def health_check():
    """Lightweight liveness probe.

    Returns 200 when the API is responsive. Includes a tiny DB touch and
    scheduler state for quick diagnostics.
    """
    # Minimal DB touch: open and close a session
    try:
        db = SessionLocal()
        db.execute(text("SELECT 1"))
    except Exception as e:
        raise HTTPException(status_code=500, detail={"status": "error", "db": str(e)})
    finally:
        try:
            db.close()
        except Exception:
            pass

    return {
        "status": "ok",
        "scheduler_running": bool(getattr(scheduler, "running", False)),
    }


@router.get("/status/balances")
async def get_current_balances(
    config_manager: ConfigManager = Depends(get_config_manager),
):
    """Fetches and returns the current portfolio balances from Binance.

    This endpoint connects to the Binance API to get the current balances of all
    assets in the account. It then calculates the approximate USD value of each
    asset and the total portfolio value.

    Args:
        config_manager: The configuration manager, injected by FastAPI.

    Returns:
        A dictionary containing the total portfolio value and a breakdown of
        balances for each asset, or an error message if keys are missing or
        invalid.
    """
    settings = config_manager.get_settings()
    api_key = config_manager.decrypt(settings.binance.api_key_encrypted)
    secret_key = config_manager.decrypt(settings.binance.secret_key_encrypted)

    if not api_key or not secret_key:
        return {"error": "As chaves de API da Binance não estão configuradas."}

    try:
        client = BinanceClient(api_key=api_key, secret_key=secret_key)
        balances = await client.get_account_balances()
        prices = await client.get_all_prices()

        base_pair = settings.base_pair
        base_to_usd = resolve_base_to_usd_rate(prices, base_pair)

        balances_with_value = {}
        total_value_base = 0.0
        total_value_usd: float | None = 0.0 if base_to_usd is not None else None

        for asset, qty in balances.items():
            if qty == 0:
                continue

            price_in_base = get_asset_base_value(prices, asset, base_pair)
            if price_in_base is None:
                continue

            value_in_base = qty * price_in_base
            price_in_usd = get_asset_usd_value(prices, asset, base_pair)
            value_usd = qty * price_in_usd if price_in_usd is not None else None

            display_value = value_usd if value_usd is not None else value_in_base
            if display_value < 1:
                continue

            entry = {
                "quantity": qty,
                "value_in_base": round(value_in_base, 2),
            }
            if value_usd is not None:
                entry["value_usd"] = round(value_usd, 2)

            balances_with_value[asset] = entry
            total_value_base += value_in_base
            if total_value_usd is not None and value_usd is not None:
                total_value_usd += value_usd

        return {
            "base_pair": base_pair,
            "base_to_usd_rate": base_to_usd,
            "total_value_in_base": round(total_value_base, 2),
            "total_value_usd": round(total_value_usd, 2) if total_value_usd is not None else None,
            "balances": balances_with_value,
        }

    except InvalidAPIKeys as e:
        return {"error": f"Chaves de API da Binance inválidas: {e.message}"}
    except Exception as e:
        return {"error": f"Ocorreu um erro: {e}"}
