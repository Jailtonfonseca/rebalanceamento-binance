from babel import Locale
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import RedirectResponse, Response

from app.core.security import decode_access_token
from app.services.config_manager import config_manager

# --- I18n Configuration ---
SUPPORTED_LOCALES = ["en", "pt_BR"]
DEFAULT_LOCALE = "en"


class I18nMiddleware(BaseHTTPMiddleware):
    """
    Handles internationalization by detecting the user's preferred language.

    The language is determined in the following order:
    1. From the 'lang' cookie, if set.
    2. From the 'Accept-Language' header of the browser.
    3. Falls back to the default locale ('en').
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # 1. Get language from cookie
        lang = request.cookies.get("lang")

        # 2. If no cookie, parse Accept-Language header
        if not lang:
            accept_language = request.headers.get("Accept-Language")
            if accept_language:
                # Find the best match from the supported locales
                lang = Locale.negotiate(
                    [loc.replace("-", "_") for loc in accept_language.split(",")],
                    SUPPORTED_LOCALES,
                    sep="-",
                )

        # 3. Fallback to default if no language is determined
        if not lang or lang not in SUPPORTED_LOCALES:
            lang = DEFAULT_LOCALE

        # Store the determined language in the request state
        request.state.language = lang
        return await call_next(request)


# A list of paths that are allowed during the setup process.
SETUP_PATHS = ["/setup", "/api/v1/setup", "/static"]

class SetupMiddleware(BaseHTTPMiddleware):
    """
    Redirects to the setup page if the application is not yet configured.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = config_manager.get_settings()
        is_on_setup_path = any(request.url.path.startswith(p) for p in SETUP_PATHS)

        # If the app is not configured and the user is not on a setup path,
        # redirect them to the setup page.
        if not settings.is_configured and not is_on_setup_path:
            return RedirectResponse(url="/setup", status_code=303)

        # If the app is already configured but the user tries to access a setup
        # path (except for static files), redirect them to the dashboard.
        if (
            settings.is_configured
            and is_on_setup_path
            and not request.url.path.startswith("/static")
        ):
            return RedirectResponse(url="/", status_code=303)

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Adds security headers to all responses.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        # A basic Content Security Policy (CSP) to mitigate XSS.
        # It allows scripts only from the same origin and the Chart.js CDN.
        # Inline styles are allowed for now, as they are used in the templates.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline'"
        )
        return response


class AuthenticationMiddleware(BaseHTTPMiddleware):
    """
    Handles user authentication for protected routes.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = config_manager.get_settings()
        request.state.user = None

        public_paths = [
            "/login",
            "/logout",
            "/setup",
            "/api/v1/setup",
            "/api/v1/auth/login",
            "/static",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        is_public_path = any(request.url.path.startswith(p) for p in public_paths)

        if settings.is_configured and not is_public_path:
            token = request.cookies.get("access_token")
            if not token:
                return RedirectResponse(url="/login")

            username = decode_access_token(token)
            if not username or username != settings.admin_user:
                response = RedirectResponse(url="/login")
                response.delete_cookie("access_token")
                return response

            request.state.user = username

        return await call_next(request)