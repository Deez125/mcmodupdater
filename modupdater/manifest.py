"""Load and read the manifest — the small index that maps versions -> mods.zip links.

Expected JSON shape (you edit this file in Drive; the app never needs recompiling):

    {
      "essential_installer_url": "https://.../EssentialInstaller.exe",   # optional
      "versions": {
        "1.21.1": { "mods_zip": "https://drive.google.com/file/d/.../view" },
        "26.1.2": { "mods_zip": "https://drive.google.com/file/d/.../view" }
      }
    }
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import List

from . import config, resources


class ManifestError(Exception):
    """Raised when the manifest can't be loaded or is malformed."""


def fetch_manifest(url: str | None = None) -> dict:
    url = url or config.manifest_source()
    if not url or url.startswith("PUT_YOUR"):
        raise ManifestError(
            "The version list isn't set up yet (MANIFEST_URL is still a placeholder)."
        )
    tmp = Path(tempfile.gettempdir()) / "mcmodupdater_manifest.json"
    try:
        resources.fetch(url, tmp)
    except Exception as e:  # network / drive / requests errors
        raise ManifestError(f"Couldn't download the version list: {e}") from e

    try:
        data = json.loads(tmp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        raise ManifestError(f"The version list file is unreadable: {e}") from e

    return _validate(data)


def _validate(data: dict) -> dict:
    if not isinstance(data, dict):
        raise ManifestError("Manifest must be a JSON object.")
    versions = data.get("versions")
    if not isinstance(versions, dict) or not versions:
        raise ManifestError("Manifest has no 'versions' entries.")
    for name, entry in versions.items():
        if not isinstance(entry, dict) or "mods_zip" not in entry:
            raise ManifestError(f"Version '{name}' is missing a 'mods_zip' link.")
    return data


def version_names(data: dict) -> List[str]:
    return list(data["versions"].keys())


def mods_zip_url(data: dict, version: str) -> str:
    entry = data["versions"].get(version)
    if not entry:
        raise ManifestError(f"Version '{version}' isn't in the manifest.")
    return entry["mods_zip"]


def essential_installer_url(data: dict) -> str | None:
    return data.get("essential_installer_url")
