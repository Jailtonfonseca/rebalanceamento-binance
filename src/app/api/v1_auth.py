from fastapi import APIRouter, Depends, Form, HTTPException
from starlette.responses import RedirectResponse

from app.core.security import create_access_token, verify_password
from app.services.config_manager import AppSettings, get_settings

router = APIRouter()

@router.post("/login")
async def login(
    username: str = Form(...),
    password: str = Form(...),
    settings: AppSettings = Depends(get_settings),
):
    """
    Handles user login, verifies credentials, and sets a session cookie.
    """
    # Check if the user is configured
    if not settings.is_configured or not settings.password_hash:
        return RedirectResponse(url="/setup", status_code=303)

    # Verify username and password
    if username != settings.admin_user or not verify_password(
        password, settings.password_hash
    ):
        # Redirect back to login with an error message
        return RedirectResponse(url="/login?error=Invalid username or password", status_code=303)

    # Create an access token
    access_token = create_access_token(data={"sub": username})

    # Set the token in a cookie and redirect to the dashboard
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        samesite="lax",
        secure=True,  # Set to True if using HTTPS
    )
    return response