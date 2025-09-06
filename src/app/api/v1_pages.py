from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.templating import templates
from app.services.config_manager import get_settings, AppSettings
from app.db.models import get_db, RebalanceRun

router = APIRouter(tags=["Frontend Pages"], include_in_schema=False)


@router.get("/")
async def get_dashboard_page(request: Request, db: Session = Depends(get_db)):
    """Serves the main dashboard page."""
    # We will add context here later (e.g., last run, current balances)
    last_run = db.query(RebalanceRun).order_by(RebalanceRun.timestamp.desc()).first()
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "last_run": last_run}
    )


@router.get("/config")
async def get_config_page(
    request: Request, settings: AppSettings = Depends(get_settings)
):
    """Serves the configuration page."""
    # Pass the current settings to the template
    return templates.TemplateResponse(
        "config.html", {"request": request, "settings": settings.dict()}
    )


@router.get("/history")
async def get_history_page(request: Request, db: Session = Depends(get_db)):
    """Serves the rebalancing history page."""
    history = (
        db.query(RebalanceRun).order_by(RebalanceRun.timestamp.desc()).limit(100).all()
    )
    return templates.TemplateResponse(
        "history.html", {"request": request, "history": history}
    )
