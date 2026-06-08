"""Drive Essential's own installer.

Essential's installer is a GUI app with no silent/CLI mode, so we can't run it
headlessly. Best flow:
  1. Download the installer .exe straight from its CDN link (kept in the manifest
     so the version can change without recompiling) into the user's Downloads
     folder, then launch it.
  2. If that direct download fails (or no link is configured), open essential.gg
     and *watch the Downloads folder* — when an `essential-installer*.exe` lands,
     launch it automatically.
Either way we then tell the user which options to click and watch the disk for the
installation folder Essential creates.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional, Set

from . import minecraft, resources

ESSENTIAL_WEBSITE = "https://essential.gg/download"
INSTALLER_GLOB = "essential-installer*.exe"


def downloads_dir() -> Path:
    return Path.home() / "Downloads"


def _filename_from_url(url: str, default: str = "essential-installer.exe") -> str:
    name = url.rstrip("/").rsplit("/", 1)[-1]
    return name if name.lower().endswith(".exe") else default


def download_installer(url: str, progress=None) -> Path:
    """Download the installer into the Downloads folder and return its path."""
    dest = downloads_dir() / _filename_from_url(url)
    return resources.fetch(url, dest, progress=progress)


def launch(path: str | Path) -> None:
    """Open the installer .exe (Windows)."""
    os.startfile(str(path))  # type: ignore[attr-defined]  # Windows-only, by design


def open_website() -> None:
    """Fallback: send the user to essential.gg to grab the installer manually."""
    import webbrowser

    webbrowser.open(ESSENTIAL_WEBSITE)


def list_installers() -> Set[Path]:
    """Current essential-installer*.exe files sitting in Downloads."""
    d = downloads_dir()
    return set(d.glob(INSTALLER_GLOB)) if d.exists() else set()


def find_new_installer(before: Set[Path]) -> Optional[Path]:
    """The newest installer that appeared in Downloads since the `before` snapshot."""
    fresh = [p for p in list_installers() if p not in before]
    return max(fresh, key=lambda p: p.stat().st_mtime) if fresh else None


def find_ready_installation(version: str) -> Optional[Path]:
    """Return the Essential install folder for `version` if it now exists on disk."""
    target = minecraft.installations_dir() / minecraft.expected_install_name(version)
    return target if target.exists() else None


def delete_installer(path: str | Path, attempts: int = 30, delay: float = 1.0) -> bool:
    """Best-effort cleanup of the downloaded installer .exe.

    Retries because Windows won't delete the file while the installer is still
    open — this gives the user time to close it. Gives up quietly after `attempts`.
    """
    p = Path(path)
    for _ in range(attempts):
        try:
            p.unlink(missing_ok=True)
            return True
        except OSError:
            time.sleep(delay)
    return False
