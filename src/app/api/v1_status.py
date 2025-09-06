from fastapi import APIRouter, Depends

from app.services.config_manager import get_config_manager, ConfigManager
from app.services.binance_client import BinanceClient, InvalidAPIKeys

router = APIRouter(tags=["Status"])


@router.get("/status/balances")
async def get_current_balances(
    config_manager: ConfigManager = Depends(get_config_manager),
):
    """
    Fetches and returns the current portfolio balances from Binance.
    """
    settings = config_manager.get_settings()
    api_key = config_manager.decrypt(settings.binance.api_key_encrypted)
    secret_key = config_manager.decrypt(settings.binance.secret_key_encrypted)

    if not api_key or not secret_key:
        return {"error": "Binance API keys are not configured."}

    try:
        client = BinanceClient(api_key=api_key, secret_key=secret_key)
        balances = await client.get_account_balances()
        # Optional: Fetch prices to show USD value
        prices = await client.get_all_prices()

        balances_with_value = {}
        total_value = 0
        for asset, qty in balances.items():
            value = 0
            if asset == settings.base_pair:
                value = qty
            elif f"{asset}{settings.base_pair}" in prices:
                value = qty * prices[f"{asset}{settings.base_pair}"]

            if value > 1:  # Only show assets with more than $1 value
                balances_with_value[asset] = {
                    "quantity": qty,
                    "value_usd": round(value, 2),
                }
                total_value += value

        return {
            "total_value_usd": round(total_value, 2),
            "balances": balances_with_value,
        }

    except InvalidAPIKeys as e:
        return {"error": f"Invalid Binance API Keys: {e.message}"}
    except Exception as e:
        return {"error": f"An error occurred: {e}"}
