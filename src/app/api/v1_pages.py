"""API endpoints for serving the frontend HTML pages.

This module contains the FastAPI routes that render and return the Jinja2
templates for the web user interface. These endpoints are not part of the
public API schema.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.templating import templates
from app.services.config_manager import get_settings, AppSettings
from app.db.models import get_db, RebalanceRun

router = APIRouter(tags=["Frontend Pages"], include_in_schema=False)


@router.get("/")
async def get_dashboard_page(request: Request, db: Session = Depends(get_db)):
    """Serves the main dashboard page.

    Args:
        request: The incoming FastAPI request.
        db: The database session, injected by FastAPI.

    Returns:
        A Jinja2 TemplateResponse for the dashboard page.
    """
    # We will add context here later (e.g., last run, current balances)
    last_run = db.query(RebalanceRun).order_by(RebalanceRun.timestamp.desc()).first()
    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "last_run": last_run}
    )


@router.get("/config")
async def get_config_page(
    request: Request, settings: AppSettings = Depends(get_settings)
):
    """Serves the configuration page.

    Args:
        request: The incoming FastAPI request.
        settings: The application settings, injected by FastAPI.

    Returns:
        A Jinja2 TemplateResponse for the configuration page.
    """
    # Pass the current settings to the template
    return templates.TemplateResponse(
        "config.html", {"request": request, "settings": settings.dict()}
    )


@router.get("/history")
async def get_history_page(request: Request, db: Session = Depends(get_db)):
    """Serves the rebalancing history page.

    Args:
        request: The incoming FastAPI request.
        db: The database session, injected by FastAPI.

    Returns:
        A Jinja2 TemplateResponse for the history page.
    """
    history = (
        db.query(RebalanceRun).order_by(RebalanceRun.timestamp.desc()).limit(100).all()
    )
    return templates.TemplateResponse(
        "history.html", {"request": request, "history": history}
    )
