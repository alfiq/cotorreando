"""Where Cotorreando keeps its files."""

import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Cotorreando"
MODELS_DIR = DATA_DIR / "models"
RECORDINGS_DIR = DATA_DIR / "recordings"
CONFIG_FILE = DATA_DIR / "settings.json"
PACKAGE_DIR = Path(__file__).resolve().parent
