"""Static configuration.

The ONLY thing baked into the compiled .exe that you (Jonah) ever need to set is
MANIFEST_URL below. Everything else — the list of versions, the download link for
each version's mods.zip — lives inside the manifest file itself, so adding a new
version never requires recompiling.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "MC Mod Updater"

# --- Branding (edit these) --------------------------------------------------
# Your server's name, shown big on the opening page.
SERVER_NAME = "Epstein's Island"
# Branding image shown on the opening page. Drop a square PNG in the project root
# (bundled into the .exe at build time). Set to None to show no image.
ICON_FILENAME = "icon.png"
# ---------------------------------------------------------------------------

# Paste the Google Drive *share link* to your manifest.json here.
# Accepts a Drive share URL, a plain https URL, or a local file path (handy for testing).
# While this still starts with "PUT_YOUR", the app runs but tells the user the
# version list isn't configured yet.
MANIFEST_URL = "https://raw.githubusercontent.com/Deez125/mcmodupdater/main/manifest.json"

# The folder-name pattern Essential creates per installation, e.g. "26.1.2 Fabric Essential".
INSTALL_SUFFIX = "Fabric Essential"


def _app_dir() -> Path:
    """Folder the app is running from (handles the PyInstaller frozen .exe)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def asset_path(name: str) -> Path:
    """Locate a bundled asset (e.g. icon.png), in dev and in the frozen .exe.

    PyInstaller unpacks --add-data files to sys._MEIPASS at runtime.
    """
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    return base / name


def icon_path() -> Path | None:
    if not ICON_FILENAME:
        return None
    p = asset_path(ICON_FILENAME)
    return p if p.exists() else None


def manifest_source() -> str:
    """Where to load the manifest from.

    Priority:
      1. $MCMODUPDATER_MANIFEST  — explicit override (testing).
      2. A local `manifest.json` when running from source (dev) — so you can test
         manifest changes before pushing. The frozen .exe skips this (it has no
         local manifest), so end users always get the remote one.
      3. MANIFEST_URL — the published remote manifest.
    """
    env = os.environ.get("MCMODUPDATER_MANIFEST")
    if env:
        return env
    if not getattr(sys, "frozen", False):
        for base in (_app_dir(), Path.cwd()):
            local = base / "manifest.json"
            if local.exists():
                return str(local)
    if MANIFEST_URL and not MANIFEST_URL.startswith("PUT_YOUR"):
        return MANIFEST_URL
    return MANIFEST_URL


def appdata_dir() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming")))


def default_minecraft_dir() -> Path:
    return appdata_dir() / ".minecraft"
