"""Time-related helpers for the application.

This module centralises utilities for working with timezone-aware datetimes to
avoid subtle bugs caused by naive timestamps.  Using a shared helper keeps the
behaviour consistent across database models and Pydantic schemas.
"""

from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return the current UTC time as a timezone-aware ``datetime``."""

    return datetime.now(timezone.utc)
