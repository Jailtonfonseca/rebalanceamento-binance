from typing import Optional
from fastapi import Depends, HTTPException, Request
from starlette.responses import RedirectResponse
from app.core.security import decode_access_token
from app.services.config_manager import AppSettings, get_settings

class AuthRedirectException(HTTPException):
    """Custom exception to handle redirecting unauthenticated users."""
    pass

def get_current_user(
    request: Request, settings: AppSettings = Depends(get_settings)
) -> Optional[str]:
    """
    A dependency to get the current user from the session token.
    If the user is not authenticated, it redirects to the login page.
    """
    token = request.cookies.get("access_token")

    if not token:
        # Using a custom exception allows us to catch this in a middleware
        # and redirect, but for now, a direct redirect is simpler.
        return RedirectResponse(url="/login")

    username = decode_access_token(token)

    if not username or username != settings.admin_user:
        # If the token is invalid or the username doesn't match the configured admin,
        # treat as unauthenticated.
        response = RedirectResponse(url="/login")
        response.delete_cookie("access_token") # Clear the invalid cookie
        return response

    return username

def get_current_user_optional(
    request: Request, settings: AppSettings = Depends(get_settings)
) -> Optional[str]:
    """
    A dependency to get the current user from the session token, but does not
    enforce authentication. Returns the username if logged in, or None otherwise.
    """
    token = request.cookies.get("access_token")
    if not token:
        return None

    username = decode_access_token(token)

    if not username or username != settings.admin_user:
        return None

    return username