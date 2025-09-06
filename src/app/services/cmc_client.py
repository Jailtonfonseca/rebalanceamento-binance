from typing import Any, Dict, Set

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

# --- Custom Exceptions ---


class CMCException(Exception):
    """Base exception for CoinMarketCap client errors."""

    def __init__(self, message: str, code: int = -1):
        self.message = message
        self.code = code
        super().__init__(f"CoinMarketCap API Error (code: {code}): {message}")


class CMCInvalidAPIKey(CMCException):
    """Exception for an invalid API key."""

    pass


# --- CoinMarketCap API Client ---


class CoinMarketCapClient:
    def __init__(
        self, api_key: str, base_url: str = "https://pro-api.coinmarketcap.com"
    ):
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
        """A generic method to send requests to the CMC API."""
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
        """Tests API key validity by checking the key info endpoint."""
        try:
            return await self._send_request("/v1/key/info")
        except CMCException as e:
            raise CMCInvalidAPIKey(
                f"API Key validation failed: {e.message}", e.code
            ) from e

    async def get_latest_listings(
        self, limit: int = 100, convert: str = "USD"
    ) -> Set[str]:
        """
        Gets the top N ranked cryptocurrencies from CoinMarketCap.
        Returns a set of their symbols.
        """
        params = {"limit": limit, "convert": convert}
        response_data = await self._send_request(
            "/v1/cryptocurrency/listings/latest", params=params
        )

        symbols = set()
        for item in response_data.get("data", []):
            symbols.add(item["symbol"])

        return symbols
