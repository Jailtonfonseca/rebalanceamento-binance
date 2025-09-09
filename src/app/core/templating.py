"""Configures and provides a Jinja2 template engine instance.

This module sets up the Jinja2Templates object used by the FastAPI application
to render HTML pages. It computes the path to the templates directory and
exports a configured `templates` instance for use in API endpoints.
"""
from fastapi.templating import Jinja2Templates
from pathlib import Path

# Path to the templates directory, relative to this file.
# templating.py -> core -> app -> src / web / templates
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "web" / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)
