"""API endpoint for retrieving the history of rebalancing runs.

This module provides the route for fetching a paginated list of all past
rebalancing runs that have been recorded in the database.
"""

from collections import defaultdict
from typing import Dict, List
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.models import get_db, RebalanceRun

router = APIRouter(tags=["History"])


# --- Pydantic Response Model ---
class RebalanceRunOut(BaseModel):
    """Pydantic model for a single rebalancing run history entry.

    This model defines the structure of a rebalance run object as it is
    returned by the API. It is configured to be compatible with ORM objects.
    """

    id: int
    run_id: str
    timestamp: datetime
    status: str
    is_dry_run: bool
    summary_message: str
    trades_executed: List | None
    errors: List[str] | None
    trigger: str
    base_pair: str

    model_config = ConfigDict(from_attributes=True)


# --- API Endpoint ---
@router.get("/history", response_model=List[RebalanceRunOut])
async def get_rebalance_history(db: Session = Depends(get_db), limit: int = 100):
    """Gets a list of past rebalancing runs from the database.

    Args:
        db: The database session, injected by FastAPI.
        limit: The maximum number of history entries to return.

    Returns:
        A list of rebalancing run objects.
    """
    history = (
        db.query(RebalanceRun)
        .order_by(RebalanceRun.timestamp.desc())
        .limit(limit)
        .all()
    )
    return history


@router.get("/history/portfolio-stats")
async def get_portfolio_statistics(db: Session = Depends(get_db)) -> Dict[str, object]:
    """Builds time-series data for the portfolio and each asset.

    Args:
        db: The database session, injected by FastAPI.

    Returns:
        A dictionary containing a list with the total portfolio value over time
        and a mapping with the historical values for each individual asset.
    """

    runs = (
        db.query(RebalanceRun)
        .order_by(RebalanceRun.timestamp.asc())
        .all()
    )

    portfolio_points: List[Dict[str, object]] = []
    asset_points: Dict[str, List[Dict[str, object]]] = defaultdict(list)

    for run in runs:
        if run.timestamp is None:
            continue

        timestamp = run.timestamp.replace(tzinfo=timezone.utc)
        timestamp_iso = timestamp.isoformat().replace("+00:00", "Z")

        total_after = run.total_value_usd_after
        if total_after is None and isinstance(run.projected_balances, dict):
            total_after = sum(
                float(
                    details.get("value_usd")
                    or details.get("value_in_base")
                    or 0.0
                )
                for details in run.projected_balances.values()
                if isinstance(details, dict)
            )

        if total_after is not None:
            portfolio_points.append(
                {
                    "timestamp": timestamp_iso,
                    "total_value_usd": round(float(total_after), 2),
                }
            )

        if not isinstance(run.projected_balances, dict):
            continue

        for asset, details in run.projected_balances.items():
            if not isinstance(details, dict):
                continue

            value_usd = details.get("value_usd")
            value_in_base = details.get("value_in_base")
            quantity = details.get("quantity")

            if value_usd is None and value_in_base is None and quantity is None:
                continue

            point: Dict[str, object] = {"timestamp": timestamp_iso}
            if value_usd is not None:
                point["value_usd"] = round(float(value_usd), 2)
            if value_in_base is not None:
                point["value_in_base"] = round(float(value_in_base), 2)
            if quantity is not None:
                point["quantity"] = float(quantity)

            asset_points[asset].append(point)

    return {
        "portfolio": portfolio_points,
        "assets": {asset: points for asset, points in sorted(asset_points.items())},
    }
