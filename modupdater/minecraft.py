"""Locate the Minecraft data, Essential installations, and their mods folders.

Essential keeps each setup in its own directory under
    %APPDATA%\\.minecraft\\installations\\<name>\\
with a per-installation `mods` subfolder. For a Fabric+Essential install of
version 26.1.2 the folder is named "26.1.2 Fabric Essential".
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional

from . import config

# AppsFolder id for the Microsoft Store version of the Minecraft Launcher.
_STORE_AUMID = "Microsoft.4297127D64EC6_8wekyb3d8bbwe!Minecraft"


def _launcher_candidates() -> List[Path]:
    pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    pf = os.environ.get("ProgramFiles", r"C:\Program Files")
    return [
        Path(pf86) / "Minecraft Launcher" / "MinecraftLauncher.exe",
        Path(pf86) / "Minecraft" / "MinecraftLauncher.exe",
        Path(pf) / "Minecraft Launcher" / "MinecraftLauncher.exe",
    ]


def find_launcher() -> Optional[Path]:
    """The Minecraft Launcher .exe, if installed in a standard location."""
    for candidate in _launcher_candidates():
        if candidate.exists():
            return candidate
    return None


def launch_minecraft() -> bool:
    """Open the Minecraft Launcher. Tries the standalone .exe first, then the
    Microsoft Store install. Returns False if neither could be started."""
    exe = find_launcher()
    if exe is not None:
        os.startfile(str(exe))  # type: ignore[attr-defined]  # Windows-only
        return True
    try:
        # Store apps launch via the shell apps-folder pseudo-path.
        subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{_STORE_AUMID}"])
        return True
    except OSError:
        return False


def minecraft_dir() -> Path:
    return config.default_minecraft_dir()


def installations_dir() -> Path:
    return minecraft_dir() / "installations"


def list_installations() -> List[Path]:
    d = installations_dir()
    if not d.exists():
        return []
    return sorted([c for c in d.iterdir() if c.is_dir()])


def mods_dir_for(installation: Path) -> Path:
    return Path(installation) / "mods"


def expected_install_name(version: str) -> str:
    return f"{version} {config.INSTALL_SUFFIX}"


def open_in_explorer(path: str | Path) -> None:
    """Open `path` in Windows Explorer (falls back to its parent if it's missing)."""
    p = Path(path)
    if not p.exists():
        p = p.parent
    p.mkdir(parents=True, exist_ok=True)
    os.startfile(str(p))  # type: ignore[attr-defined]  # Windows-only, by design


def find_installation_for_version(version: str) -> Optional[Path]:
    """Best-effort match of a manifest version to an on-disk Essential install."""
    installs = list_installations()
    target = expected_install_name(version).lower()
    # 1. exact "<version> Fabric Essential"
    for inst in installs:
        if inst.name.lower() == target:
            return inst
    # 2. looser: the version string appears in the folder name
    for inst in installs:
        if version.lower() in inst.name.lower():
            return inst
    return None
