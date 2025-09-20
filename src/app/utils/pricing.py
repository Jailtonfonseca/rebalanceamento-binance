"""Utility helpers for working with asset price conversions.

These helpers centralise the logic for converting between different quote
currencies using the ticker price map returned by Binance. They make it easier
to express values in the configured base pair as well as in USD, which we use
for reporting and for enforcing trade thresholds.
"""
from __future__ import annotations

from typing import Mapping, Optional

STABLE_COINS = ("USDT", "BUSD", "USDC", "TUSD")


def _get_rate(
    prices: Mapping[str, float], from_asset: str, to_asset: str
) -> Optional[float]:
    """Resolve the conversion rate between two assets if available.

    The Binance price map exposes both direct and inverse pairs. This helper
    checks for both directions and normalises the result to be the price of one
    unit of ``from_asset`` denominated in ``to_asset``.
    """
    if from_asset == to_asset:
        return 1.0

    direct_symbol = f"{from_asset}{to_asset}"
    if direct_symbol in prices:
        price = prices[direct_symbol]
        return float(price) if price not in (None, 0) else None

    inverse_symbol = f"{to_asset}{from_asset}"
    if inverse_symbol in prices:
        price = prices[inverse_symbol]
        if price in (None, 0):
            return None
        return 1 / float(price)

    return None


def resolve_base_to_usd_rate(
    prices: Mapping[str, float], base_pair: str
) -> Optional[float]:
    """Resolve how many USD one unit of ``base_pair`` is worth.

    We first treat the most common USD-pegged stable coins as $1. If the base
    pair is another crypto (e.g. BTC) we attempt to convert it to one of the
    stable coins and treat that as USD.
    """
    base_pair = base_pair.upper()

    if base_pair in STABLE_COINS:
        return 1.0

    for stable in STABLE_COINS:
        rate = _get_rate(prices, base_pair, stable)
        if rate is not None:
            return rate

    # As a last resort try to convert directly to USD if such a pair exists.
    fallback_rate = _get_rate(prices, base_pair, "USD")
    return fallback_rate


def get_asset_base_value(
    prices: Mapping[str, float], asset: str, base_pair: str
) -> Optional[float]:
    """Return the price of ``asset`` denominated in the ``base_pair``.

    The function returns ``1`` when ``asset`` already matches ``base_pair``.
    """
    asset = asset.upper()
    base_pair = base_pair.upper()

    if asset == base_pair:
        return 1.0

    return _get_rate(prices, asset, base_pair)


def get_asset_usd_value(
    prices: Mapping[str, float], asset: str, base_pair: str
) -> Optional[float]:
    """Return the price of ``asset`` denominated in USD.

    The helper first tries to convert the asset into the configured base pair
    and, if successful, uses :func:`resolve_base_to_usd_rate` to convert the
    base pair into USD. When a direct USD (or USD stable coin) pair is
    available we use it directly.
    """
    asset = asset.upper()
    base_pair = base_pair.upper()

    # Direct stable-coin lookups take precedence so we avoid compounding
    # potential rounding errors when both routes exist.
    for stable in (*STABLE_COINS, "USD"):
        direct_rate = _get_rate(prices, asset, stable)
        if direct_rate is not None:
            return direct_rate

    base_rate = get_asset_base_value(prices, asset, base_pair)
    if base_rate is None:
        return None

    base_to_usd = resolve_base_to_usd_rate(prices, base_pair)
    if base_to_usd is None:
        return None

    return base_rate * base_to_usd
