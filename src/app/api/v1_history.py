from typing import List
from datetime import datetime
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import get_db, RebalanceRun

router = APIRouter(tags=["History"])


# --- Pydantic Response Model ---
class RebalanceRunOut(BaseModel):
    id: int
    run_id: str
    timestamp: datetime
    status: str
    is_dry_run: bool
    summary_message: str
    trades_executed: List | None
    errors: List[str] | None

    class Config:
        orm_mode = True


# --- API Endpoint ---
@router.get("/history", response_model=List[RebalanceRunOut])
async def get_rebalance_history(db: Session = Depends(get_db), limit: int = 100):
    """
    Returns a list of past rebalancing runs from the database.
    """
    history = (
        db.query(RebalanceRun)
        .order_by(RebalanceRun.timestamp.desc())
        .limit(limit)
        .all()
    )
    return history
