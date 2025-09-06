import time
import hmac
import hashlib
import json
from urllib.parse import urlencode
from typing import Any, Dict, List, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

# --- Custom Exceptions ---


class BinanceException(Exception):
    """Base exception for Binance client errors."""

    def __init__(self, message: str, code: int = -1):
        self.message = message
        self.code = code
        super().__init__(f"Binance API Error (code: {code}): {message}")


class InvalidAPIKeys(BinanceException):
    """Exception for invalid API keys."""

    pass


# --- Binance API Client ---


class BinanceClient:
    def __init__(
        self, api_key: str, secret_key: str, base_url: str = "https://api.binance.com"
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        self._exchange_info_cache: Optional[Dict[str, Any]] = None

    def _generate_signature(self, data: Dict[str, Any]) -> str:
        """Generates a HMAC-SHA256 signature for a request."""
        return hmac.new(
            self.secret_key.encode("utf-8"),
            urlencode(data).encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _send_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict[str, Any]] = None,
        signed: bool = False,
    ):
        """A generic method to send requests to the Binance API."""
        params = params or {}
        headers = {"X-MBX-APIKEY": self.api_key}

        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["signature"] = self._generate_signature(params)

        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method, url, params=params, headers=headers
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                # Parse the error response from Binance
                error_data = e.response.json()
                error_code = error_data.get("code", -1)
                error_msg = error_data.get("msg", "An unknown error occurred.")
                if error_code == -2014:
                    raise InvalidAPIKeys(
                        f"Invalid API keys provided. {error_msg}", error_code
                    ) from e
                raise BinanceException(error_msg, error_code) from e

    async def test_connectivity(self) -> Dict[str, Any]:
        """Tests API key validity by fetching account information."""
        try:
            return await self._send_request("GET", "/api/v3/account", signed=True)
        except BinanceException as e:
            # Re-raise with a more specific message if it's likely a key issue
            if e.code in [-2014, -2015, -1022]:
                raise InvalidAPIKeys(
                    f"API Key validation failed: {e.message}", e.code
                ) from e
            raise

    async def get_account_balances(self) -> Dict[str, float]:
        """Fetches all asset balances for the account."""
        account_info = await self.test_connectivity()
        balances = {}
        for asset in account_info.get("balances", []):
            free_balance = float(asset["free"])
            if free_balance > 0:
                balances[asset["asset"]] = free_balance
        return balances

    async def get_exchange_info(
        self, symbols: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Fetches trading rules, optionally filtering by symbols."""
        if self._exchange_info_cache:
            return self._exchange_info_cache

        params = {"symbols": json.dumps(symbols)} if symbols else {}
        info = await self._send_request("GET", "/api/v3/exchangeInfo", params=params)

        # Cache the result by symbol for easy lookup
        self._exchange_info_cache = {item["symbol"]: item for item in info["symbols"]}
        return self._exchange_info_cache

    def get_symbol_filter(
        self, symbol: str, filter_type: str
    ) -> Optional[Dict[str, Any]]:
        """Helper to get a specific filter from cached exchange info."""
        if not self._exchange_info_cache:
            raise RuntimeError("Call get_exchange_info() before using this method.")

        symbol_info = self._exchange_info_cache.get(symbol)
        if not symbol_info:
            return None

        for f in symbol_info.get("filters", []):
            if f["filterType"] == filter_type:
                return f
        return None

    async def get_all_prices(self) -> Dict[str, float]:
        """Fetches the latest price for all symbols."""
        prices_data = await self._send_request("GET", "/api/v3/ticker/price")
        return {item["symbol"]: float(item["price"]) for item in prices_data}

    async def create_order(
        self, symbol: str, side: str, quantity: float, test: bool = False
    ) -> Dict[str, Any]:
        """Creates a market order."""
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,
        }
        endpoint = "/api/v3/order/test" if test else "/api/v3/order"
        return await self._send_request("POST", endpoint, params=params, signed=True)
