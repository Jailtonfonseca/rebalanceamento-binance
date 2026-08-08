import logging
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

# Constants
BINANCE_API_URL = "https://api.binance.com/api/v3"
TRADING_FEE = 0.001  # 0.1% trading fee per trade
COMMON_QUOTE_ASSETS = (
    "USDT",
    "FDUSD",
    "USDC",
    "BUSD",
    "TUSD",
    "BTC",
    "ETH",
    "BNB",
    "TRY",
    "EUR",
    "BRL",
    "GBP",
)

logger = logging.getLogger(__name__)


class ArbitrageService:
    """
    A service to find triangular arbitrage opportunities on Binance.
    """

    def __init__(self, client: Optional[httpx.AsyncClient] = None):
        """
        Initializes the ArbitrageService.

        Args:
            client: An optional httpx.AsyncClient for making HTTP requests.
        """
        self.client = client or httpx.AsyncClient()
        self.prices: Dict[str, float] = {}
        self.symbols: List[str] = []

    @retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
    async def fetch_market_data(self) -> None:
        """
        Fetches all symbol prices from Binance and updates the internal price cache.
        Raises an exception if the request fails after multiple retries.
        """
        try:
            response = await self.client.get(f"{BINANCE_API_URL}/ticker/price")
            response.raise_for_status()
            data = response.json()

            self.prices = {item["symbol"]: float(item["price"]) for item in data}
            self.symbols = list(self.prices.keys())
            logger.info(
                "Successfully fetched %s price tickers from Binance.", len(self.prices)
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 451:
                logger.warning(
                    "Failed to fetch market data from Binance due to legal restrictions "
                    "(451 Client Error)."
                )
                self.prices = {}
                self.symbols = []
            else:
                logger.error("HTTP error fetching Binance market data: %s", e)
                raise
        except Exception as e:
            logger.error(
                "An unexpected error occurred while fetching market data: %s", e
            )
            raise

    def _split_symbol(self, symbol: str) -> Optional[Tuple[str, str]]:
        """Splits a Binance symbol into base and quote assets.

        Binance ticker symbols are concatenated without a separator. The previous
        implementation assumed all quote assets had three characters, which
        misread symbols such as BTCUSDT as (BTCU, SDT). Prefer known quote assets
        so 4+ character quotes are parsed correctly.
        """
        for quote in sorted(COMMON_QUOTE_ASSETS, key=len, reverse=True):
            if symbol.endswith(quote) and len(symbol) > len(quote):
                return symbol[: -len(quote)], quote
        return None

    def _extract_assets(self) -> List[str]:
        """Extracts unique asset codes from known Binance ticker symbols."""
        assets = set()
        for symbol in self.symbols:
            split_symbol = self._split_symbol(symbol)
            if split_symbol:
                base, quote = split_symbol
                assets.update((base, quote))
        return sorted(assets)

    def _get_triangular_paths(self, assets: List[str]) -> List[Tuple[str, str, str]]:
        """
        Generates all possible triangular arbitrage paths from a given list of assets.
        A path is a tuple of three assets, e.g., (BTC, ETH, BNB).
        """
        return list(combinations(assets, 3))

    def _conversion_rate(self, from_asset: str, to_asset: str) -> Optional[float]:
        """Returns the executable conversion rate from one asset to another.

        If Binance lists FROMTO, selling one unit of FROM buys price units of TO.
        If Binance lists TOFROM, converting FROM to TO requires the inverse price.
        """
        direct = self.prices.get(f"{from_asset}{to_asset}")
        if direct and direct > 0:
            return direct

        inverse = self.prices.get(f"{to_asset}{from_asset}")
        if inverse and inverse > 0:
            return 1 / inverse

        return None

    def _calculate_profitability(self, path: Tuple[str, str, str]) -> Optional[Dict]:
        """Calculates the potential profit of a single triangular arbitrage path."""
        a, b, c = path
        rate1 = self._conversion_rate(a, b)
        rate2 = self._conversion_rate(b, c)
        rate3 = self._conversion_rate(c, a)

        if not (rate1 and rate2 and rate3):
            return None

        profit_margin = (rate1 * rate2 * rate3) * ((1 - TRADING_FEE) ** 3)
        if profit_margin <= 1:
            return None

        return {
            "path": f"{a} -> {b} -> {c} -> {a}",
            "profit_margin_percent": (profit_margin - 1) * 100,
            "rates": {f"{b}/{a}": rate1, f"{c}/{b}": rate2, f"{a}/{c}": rate3},
        }

    async def find_opportunities(self) -> List[Dict]:
        """Finds all profitable triangular arbitrage opportunities."""
        await self.fetch_market_data()

        if not self.prices:
            logger.warning("Price data is not available. Skipping arbitrage check.")
            return []

        assets_to_check = [
            asset
            for asset in self._extract_assets()
            if asset in {"BTC", "ETH", "USDT", "BNB", "XRP", "ADA"}
        ]

        if len(assets_to_check) < 3:
            logger.warning("Not enough assets to check for triangular arbitrage.")
            return []

        profitable_opportunities = []
        for path in self._get_triangular_paths(assets_to_check):
            opportunity = self._calculate_profitability(path)
            if opportunity:
                profitable_opportunities.append(opportunity)

        profitable_opportunities.sort(
            key=lambda x: x["profit_margin_percent"], reverse=True
        )
        return profitable_opportunities
