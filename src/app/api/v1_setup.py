import logging
import bcrypt
from fastapi import APIRouter, Depends, Form, Request, HTTPException
from starlette.responses import RedirectResponse

from app.core.security import create_access_token, get_password_hash
from app.services.config_manager import ConfigManager, get_config_manager, AppSettings

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/setup")
async def handle_initial_setup(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    config_manager: ConfigManager = Depends(get_config_manager),
):
    """
    Handles the initial administrator account setup, saves the new credentials,
    and automatically logs the user in.
    """
    settings = config_manager.get_settings()
    if settings.is_configured:
        raise HTTPException(
            status_code=403, detail="Application is already configured."
        )

    # Hash the password
    hashed_password = get_password_hash(password)

    # Update the settings
    new_settings_data = settings.model_dump()
    new_settings_data["admin_user"] = username
    new_settings_data["password_hash"] = hashed_password
    new_settings_data["is_configured"] = True

    updated_settings = AppSettings(**new_settings_data)
    config_manager.save_settings(updated_settings)
    logger.info(f"Initial setup complete. Admin user '{username}' created.")

    # Automatically log the user in by creating a session token
    access_token = create_access_token(data={"sub": username})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
    )
    return response