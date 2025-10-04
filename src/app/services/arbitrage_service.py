import logging
from itertools import combinations
from typing import List, Dict, Tuple, Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_fixed

# Constants
BINANCE_API_URL = "https://api.binance.com/api/v3"
TRADING_FEE = 0.001  # 0.1% trading fee per trade

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

            self.prices = {item['symbol']: float(item['price']) for item in data}
            self.symbols = list(self.prices.keys())
            logger.info(f"Successfully fetched {len(self.prices)} price tickers from Binance.")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 451:
                logger.warning(f"Failed to fetch market data from Binance due to legal restrictions (451 Client Error).")
                self.prices = {}
                self.symbols = []
            else:
                logger.error(f"HTTP error fetching Binance market data: {e}")
                raise
        except Exception as e:
            logger.error(f"An unexpected error occurred while fetching market data: {e}")
            raise

    def _get_triangular_paths(self, assets: List[str]) -> List[Tuple[str, str, str]]:
        """
        Generates all possible triangular arbitrage paths from a given list of assets.
        A path is a tuple of three assets, e.g., (BTC, ETH, BNB).
        """
        return list(combinations(assets, 3))

    def _calculate_profitability(self, path: Tuple[str, str, str]) -> Optional[Dict]:
        """
        Calculates the potential profit of a single triangular arbitrage path.

        The path consists of three assets (A, B, C) and involves three trades:
        1. A -> B
        2. B -> C
        3. C -> A

        Args:
            path: A tuple of three asset symbols (e.g., ('BTC', 'ETH', 'BNB')).

        Returns:
            A dictionary with the opportunity details if it's profitable, otherwise None.
        """
        try:
            a, b, c = path
            rate1_forward = self.prices.get(f"{b}{a}")
            rate2_forward = self.prices.get(f"{c}{b}")
            rate3_forward = self.prices.get(f"{a}{c}")

            if rate1_forward and rate2_forward and rate3_forward:
                profit_margin = (rate1_forward * rate2_forward * rate3_forward) * ((1 - TRADING_FEE) ** 3)
                if profit_margin > 1:
                    return {
                        "path": f"{a} -> {b} -> {c} -> {a}",
                        "profit_margin_percent": (profit_margin - 1) * 100,
                        "rates": {f"{b}/{a}": rate1_forward, f"{c}/{b}": rate2_forward, f"{a}/{c}": rate3_forward},
                    }
        except Exception:
            # This can happen if a direct pair is not found.
            pass

        return None

    async def find_opportunities(self) -> List[Dict]:
        """
        Finds all profitable triangular arbitrage opportunities.

        Returns:
            A list of dictionaries, where each dictionary represents a profitable opportunity.
        """
        await self.fetch_market_data()

        if not self.prices:
            logger.warning("Price data is not available. Skipping arbitrage check.")
            return []

        # Extract unique assets from the available symbols
        unique_assets = sorted(list(set(asset for symbol in self.symbols for asset in [symbol[:-3], symbol[-3:]])))

        # For performance, let's limit the number of assets to check.
        # Here we can filter for top assets by volume or other criteria in a real scenario.
        # For this simulation, we'll take a subset.
        assets_to_check = [asset for asset in unique_assets if asset in {"BTC", "ETH", "USDT", "BNB", "XRP", "ADA"}]

        if len(assets_to_check) < 3:
            logger.warning("Not enough assets to check for triangular arbitrage.")
            return []

        paths = self._get_triangular_paths(assets_to_check)
        profitable_opportunities = []

        for path in paths:
            opportunity = self._calculate_profitability(path)
            if opportunity:
                profitable_opportunities.append(opportunity)

        # Sort by highest profit
        profitable_opportunities.sort(key=lambda x: x["profit_margin_percent"], reverse=True)

        return profitable_opportunities


# Example usage:
# if __name__ == "__main__":
#     import asyncio
#
#     async def main():
#         service = ArbitrageService()
#         opportunities = await service.find_opportunities()
#         if opportunities:
#             print("Found profitable opportunities:")
#             for opp in opportunities:
#                 print(
#                     f"  Path: {opp['path']}, "
#                     f"Profit: {opp['profit_margin_percent']:.4f}%"
#                 )
#         else:
#             print("No profitable arbitrage opportunities found.")
#
#     asyncio.run(main())