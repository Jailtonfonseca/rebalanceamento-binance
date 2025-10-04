"""API endpoints for serving the frontend HTML pages.

This module contains the FastAPI routes that render and return the Jinja2
templates for the web user interface. These endpoints are not part of the
public API schema.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.templating import templates
from app.services.arbitrage_service import TRADING_FEE
from app.services.config_manager import get_settings, AppSettings
from app.db.models import get_db, RebalanceRun

router = APIRouter(tags=["Frontend Pages"], include_in_schema=False)


def _sorted_projected_balances(projected_balances):
    """Return projected balances sorted by USD value in descending order."""

    if not isinstance(projected_balances, dict):
        return []

    normalized_items = []
    for asset, raw_details in projected_balances.items():
        details = raw_details if isinstance(raw_details, dict) else {}
        normalized_items.append((asset, details))

    def balance_value(item):
        _, details = item
        value = details.get("value_usd", 0.0)
        try:
            return float(value or 0.0)
        except (TypeError, ValueError):
            return 0.0

    return sorted(normalized_items, key=balance_value, reverse=True)


@router.get("/")
async def get_dashboard_page(request: Request, db: Session = Depends(get_db)):
    """Serves the main dashboard page.

    Args:
        request: The incoming FastAPI request.
        db: The database session, injected by FastAPI.

    Returns:
        A Jinja2 TemplateResponse for the dashboard page.
    """
    last_run = db.query(RebalanceRun).order_by(RebalanceRun.timestamp.desc()).first()

    sorted_balances = []
    if last_run is not None:
        projected_balances = getattr(last_run, "projected_balances", None)
        sorted_balances = _sorted_projected_balances(projected_balances)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "last_run": last_run,
            "sorted_balances": sorted_balances,
        },
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
        "config.html", {"request": request, "settings": settings.model_dump()}
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
        db.query(RebalanceRun)
        .order_by(RebalanceRun.timestamp.desc())
        .limit(100)
        .all()
    )

    for run in history:
        projected_balances = getattr(run, "projected_balances", None)
        run.sorted_balances = _sorted_projected_balances(projected_balances)

    return templates.TemplateResponse(
        "history.html", {"request": request, "history": history}
    )


@router.get("/arbitrage")
async def get_arbitrage_page(request: Request):
    """Serves the arbitrage simulator page.

    Args:
        request: The incoming FastAPI request.

    Returns:
        A Jinja2 TemplateResponse for the arbitrage page.
    """
    return templates.TemplateResponse(
        "arbitrage.html",
        {
            "request": request,
            "TRADING_FEE": TRADING_FEE,
        },
    )
