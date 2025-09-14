"""A client for interacting with the CoinMarketCap (CMC) API.

This module provides a high-level, asynchronous client for the CMC API,
specifically for fetching cryptocurrency listing data. It includes custom
exceptions for handling API-specific errors.
"""

from typing import Any, Dict, Set

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

# --- Custom Exceptions ---


class CMCException(Exception):
    """Base exception for CoinMarketCap client errors.

    Attributes:
        message: The error message from the API.
        code: The error code from the API.
    """

    def __init__(self, message: str, code: int = -1):
        self.message = message
        self.code = code
        super().__init__(f"CoinMarketCap API Error (code: {code}): {message}")


class CMCInvalidAPIKey(CMCException):
    """Exception raised for an invalid or exhausted CoinMarketCap API key.

    This is a specialized subclass of CMCException indicating a problem with
    API key authentication.
    """

    pass


# --- CoinMarketCap API Client ---


class CoinMarketCapClient:
    """An asynchronous client for the CoinMarketCap API.

    This client handles making requests to the CMC API, including authentication
    and error handling.

    Attributes:
        api_key: The API key for CoinMarketCap.
        base_url: The base URL for the CMC API.
        headers: A dictionary of headers used for API requests.
    """

    def __init__(
        self, api_key: str, base_url: str = "https://pro-api.coinmarketcap.com"
    ):
        """Initializes the CoinMarketCapClient.

        Args:
            api_key: The API key for CoinMarketCap.
            base_url: The base URL for the CMC API endpoint.
        """
        self.api_key = api_key
        self.base_url = base_url
        self.headers = {
            "X-CMC_PRO_API_KEY": self.api_key,
            "Accept": "application/json",
        }

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _send_request(
        self, endpoint: str, params: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Sends a request to the CMC API, with retries on failure.

        This is a generic internal method that handles sending the HTTP request
        and processing the response for errors.

        Args:
            endpoint: The API endpoint path (e.g., '/v1/key/info').
            params: A dictionary of request parameters.

        Returns:
            The JSON response data from the API as a dictionary.

        Raises:
            CMCInvalidAPIKey: If the API key is invalid.
            CMCException: For other API-related errors.
        """
        url = f"{self.base_url}{endpoint}"
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()

                # Check for API errors in the response body
                status = data.get("status", {})
                if status.get("error_code") != 0:
                    error_message = status.get("error_message", "Unknown API error.")
                    error_code = status.get("error_code")
                    if error_code in [
                        1001,
                        1002,
                    ]:  # "API key invalid" or "API key plan exhausted"
                        raise CMCInvalidAPIKey(error_message, error_code)
                    raise CMCException(error_message, error_code)

                return data
            except httpx.HTTPStatusError as e:
                # This handles network-level errors (e.g., 401, 403)
                error_data = e.response.json().get("status", {})
                error_code = error_data.get("error_code", e.response.status_code)
                error_msg = error_data.get("error_message", "An HTTP error occurred.")
                if e.response.status_code == 401:
                    raise CMCInvalidAPIKey(error_msg, error_code) from e
                raise CMCException(error_msg, error_code) from e

    async def test_connectivity(self) -> Dict[str, Any]:
        """Tests connectivity and API key validity.

        This method makes a request to the key info endpoint. A successful
        response indicates a valid API key and a working connection.

        Returns:
            The raw key information dictionary from the API.

        Raises:
            CMCInvalidAPIKey: If the API key is invalid or exhausted.
        """
        try:
            return await self._send_request("/v1/key/info")
        except CMCException as e:
            raise CMCInvalidAPIKey(
                f"API Key validation failed: {e.message}", e.code
            ) from e

    async def get_latest_listings(
        self, limit: int = 100, convert: str = "USD"
    ) -> Set[str]:
        """Gets the top N ranked cryptocurrencies from CoinMarketCap.

        This method fetches the latest listings and returns a set of symbols
        for the top-ranked assets.

        Args:
            limit: The number of top cryptocurrencies to return.
            convert: The fiat currency to convert to (e.g., 'USD').

        Returns:
            A set of cryptocurrency symbols (e.g., {'BTC', 'ETH'}).
        """
        params = {"limit": limit, "convert": convert}
        response_data = await self._send_request(
            "/v1/cryptocurrency/listings/latest", params=params
        )

        symbols = set()
        for item in response_data.get("data", []):
            symbols.add(item["symbol"])

        return symbols
