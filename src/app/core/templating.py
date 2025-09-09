from fastapi.templating import Jinja2Templates
from pathlib import Path

# Path to the templates directory, relative to this file.
# templating.py -> core -> app -> src / web / templates
TEMPLATES_DIR = Path(__file__).parent.parent.parent / "web" / "templates"

templates = Jinja2Templates(directory=TEMPLATES_DIR)
