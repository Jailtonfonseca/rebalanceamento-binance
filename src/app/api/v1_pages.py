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
    last_run = db.query(RebalanceRun).order_by(RebalanceRun.timestamp.desc()).first()

    sorted_balances = []
    if last_run is not None:
        projected_balances = getattr(last_run, "projected_balances", None)

        if isinstance(projected_balances, dict):
            def safe_value_usd(item: tuple[str, object]) -> float:
                """Return a comparable USD value for ordering projected balances."""

                _, details = item

                if isinstance(details, dict):
                    value = details.get("value_usd", 0.0)
                else:
                    value = 0.0

                try:
                    return float(value or 0.0)
                except (TypeError, ValueError):
                    return 0.0

            sorted_balances = sorted(
                projected_balances.items(), key=safe_value_usd, reverse=True
            )

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
        db.query(RebalanceRun).order_by(RebalanceRun.timestamp.desc()).limit(100).all()
    )
    return templates.TemplateResponse(
        "history.html", {"request": request, "history": history}
    )
