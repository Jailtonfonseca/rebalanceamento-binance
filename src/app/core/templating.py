"""Configures and provides a Jinja2 template engine instance.

This module sets up the Jinja2Templates object used by the FastAPI application
to render HTML pages. It computes the path to the templates directory and
exports a configured `templates` instance for use in API endpoints.
"""

from pathlib import Path

from babel.support import Translations
from fastapi.templating import Jinja2Templates as _Jinja2Templates
from starlette.requests import Request

# Path to the templates directory, relative to this file.
# templating.py -> core -> app -> src / web / templates
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "web" / "templates"
LOCALE_DIR = Path(__file__).parent.parent / "locales"


class Jinja2Templates(_Jinja2Templates):
    """
    A custom Jinja2Templates class that handles i18n translations automatically.
    """
    def TemplateResponse(self, name: str, context: dict, *args, **kwargs):
        request = context.get("request")
        if isinstance(request, Request):
            language = getattr(request.state, "language", "en")
            try:
                translations = Translations.load(str(LOCALE_DIR), [language], domain="messages")
                self.env.install_gettext_translations(translations)
            except FileNotFoundError:
                # Fallback to no translations if the .mo file doesn't exist yet
                self.env.install_null_translations()
        return super().TemplateResponse(name, context, *args, **kwargs)


# Initialize the custom Jinja2Templates instance
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# Add the i18n extension to the Jinja2 environment
templates.env.add_extension("jinja2.ext.i18n")