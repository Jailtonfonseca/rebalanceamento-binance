"""API endpoint for retrieving the history of rebalancing runs.

This module provides the route for fetching a paginated list of all past
rebalancing runs that have been recorded in the database.
"""
from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
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

    class Config:
        """Pydantic configuration."""
        orm_mode = True


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
