"""A client for interacting with the Binance API.

This module provides a high-level, asynchronous client for the Binance REST API,
including methods for account management, fetching market data, and placing orders.
It also defines custom exceptions for handling API-specific errors.
"""
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
    """Base exception for Binance client errors.

    Attributes:
        message: The error message from the API.
        code: The error code from the API.
    """

    def __init__(self, message: str, code: int = -1):
        self.message = message
        self.code = code
        super().__init__(f"Binance API Error (code: {code}): {message}")


class InvalidAPIKeys(BinanceException):
    """Exception raised for invalid or expired API keys.

    This is a specialized subclass of BinanceException that indicates a problem
    with authentication, specifically the API key or secret.
    """

    pass


# --- Binance API Client ---


class BinanceClient:
    """An asynchronous client for the Binance API.

    This client handles request signing, error handling, and API interactions
    such as fetching account data, market data, and executing orders.

    Attributes:
        api_key: The public API key for Binance.
        secret_key: The secret key for signing requests.
        base_url: The base URL for the Binance API.
    """
    def __init__(
        self, api_key: str, secret_key: str, base_url: str = "https://api.binance.com"
    ):
        """Initializes the BinanceClient.

        Args:
            api_key: The public API key for Binance.
            secret_key: The secret key for signing requests.
            base_url: The base URL for the Binance API endpoint.
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        self._exchange_info_cache: Optional[Dict[str, Any]] = None

    def _generate_signature(self, data: Dict[str, Any]) -> str:
        """Generates a HMAC-SHA256 signature for a request payload.

        Args:
            data: A dictionary of parameters to be signed.

        Returns:
            The hexadecimal HMAC-SHA256 signature.
        """
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
    ) -> Dict[str, Any] | List[Dict[str, Any]]:
        """Sends a request to the Binance API, with retries on failure.

        This is a generic internal method that handles request signing,
        sending the HTTP request, and basic error handling.

        Args:
            method: The HTTP method (e.g., 'GET', 'POST').
            endpoint: The API endpoint path (e.g., '/api/v3/account').
            params: A dictionary of request parameters.
            signed: Whether the request requires a signature.

        Returns:
            The JSON response from the API as a dictionary or list.

        Raises:
            InvalidAPIKeys: If the API keys are invalid.
            BinanceException: For other API-related errors.
        """
        params = params or {}
        headers = {"X-MBX-APIKEY": self.api_key}
        url = f"{self.base_url}{endpoint}"

        async with httpx.AsyncClient() as client:
            try:
                # Create a copy to avoid modifying the original dict, which is crucial for retry logic.
                params_to_send = (params or {}).copy()

                # Signature and timestamp must be generated for each attempt
                if signed:
                    params_to_send["recvWindow"] = 10000
                    params_to_send["timestamp"] = int(time.time() * 1000)
                    params_to_send["signature"] = self._generate_signature(params_to_send)

                request_kwargs = {"headers": headers}
                if method.upper() in ("POST", "PUT", "DELETE"):
                    request_kwargs["data"] = params_to_send
                else:
                    request_kwargs["params"] = params_to_send

                response = await client.request(method, url, **request_kwargs)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                # Parse the error response from Binance
                error_data = e.response.json()
                error_code = error_data.get("code", -1)
                error_msg = error_data.get("msg", "An unknown error occurred.")

                # -2014: Invalid API key format. -2015: Invalid API key, IP, or permissions. -1022: Signature mismatch.
                if error_code in [-2014, -2015, -1022]:
                    raise InvalidAPIKeys(
                        f"API Key validation failed: {error_msg}", error_code
                    ) from e
                raise BinanceException(error_msg, error_code) from e

    async def test_connectivity(self) -> Dict[str, Any]:
        """Tests connectivity and API key validity by fetching account info.

        This method makes a signed request to the account endpoint. A successful
        response indicates valid API keys and a working connection.

        Returns:
            The raw account information dictionary from the API.

        Raises:
            InvalidAPIKeys: If the API keys are invalid or lack permissions.
            BinanceException: For other API or connection errors.
        """
        # The specific error handling is now centralized in _send_request.
        # We just need to call the endpoint.
        return await self._send_request("GET", "/api/v3/account", signed=True)

    async def get_account_balances(self) -> Dict[str, float]:
        """Fetches all non-zero asset balances for the account.

        This method retrieves the account information and filters it to return
        only the assets with a 'free' balance greater than zero.

        Returns:
            A dictionary mapping asset symbols to their free balance as a float.
        """
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
        """Fetches exchange trading rules and symbol information.

        This method retrieves comprehensive information about trading rules,
        symbol details, and filters. The result is cached for subsequent calls
        to avoid redundant API requests.

        Args:
            symbols: An optional list of symbols to fetch information for.
                     If None, information for all symbols is fetched.

        Returns:
            A dictionary mapping symbols to their exchange information.
        """
        if self._exchange_info_cache:
            return self._exchange_info_cache

        endpoint = "/api/v3/exchangeInfo"
        params = {}
        if symbols:
            # Binance's API for this endpoint expects the 'symbols' parameter to be a
            # string that looks like a JSON array, e.g., '["BTCUSDT","ETHUSDT"]'.
            # The httpx library, by default, URL-encodes the `[` `]` and `"` characters,
            # which causes the Binance API to reject the request.
            # To work around this, we manually append the query string for the 'symbols'
            # parameter and pass an empty 'params' dict to the request method for
            # other parameters if needed in the future.
            symbols_json_string = json.dumps(symbols)
            endpoint = f"{endpoint}?symbols={symbols_json_string}"

        info = await self._send_request("GET", endpoint, params=params)

        # Cache the result by symbol for easy lookup
        self._exchange_info_cache = {item["symbol"]: item for item in info["symbols"]}
        return self._exchange_info_cache

    def get_symbol_filter(
        self, symbol: str, filter_type: str
    ) -> Optional[Dict[str, Any]]:
        """Retrieves a specific filter for a symbol from cached exchange info.

        This is a helper method that must be called after get_exchange_info().

        Args:
            symbol: The trading symbol (e.g., 'BTCUSDT').
            filter_type: The type of filter to retrieve (e.g., 'LOT_SIZE').

        Returns:
            A dictionary representing the filter, or None if not found.

        Raises:
            RuntimeError: If exchange info has not been cached first.
        """
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
        """Fetches the latest market price for all symbols.

        Returns:
            A dictionary mapping each symbol to its latest price as a float.
        """
        prices_data = await self._send_request("GET", "/api/v3/ticker/price")
        return {item["symbol"]: float(item["price"]) for item in prices_data}

    async def create_order(
        self, symbol: str, side: str, quantity: str, test: bool = False
    ) -> Dict[str, Any]:
        """Creates a market order.

        Args:
            symbol: The trading symbol (e.g., 'BTCUSDT').
            side: The order side ('BUY' or 'SELL').
            quantity: The amount to buy or sell. Must be a plain decimal string.
            test: If True, sends a test order that is validated but not
                  executed. Defaults to False.

        Returns:
            The API response from the order creation endpoint.
        """
        params = {
            "symbol": symbol,
            "side": side.upper(),
            "type": "MARKET",
            "quantity": quantity,
        }
        endpoint = "/api/v3/order/test" if test else "/api/v3/order"
        return await self._send_request("POST", endpoint, params=params, signed=True)
