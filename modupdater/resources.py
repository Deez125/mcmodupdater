"""Fetch a resource (manifest or zip) to a local file, regardless of where it lives.

Handles three source kinds transparently:
  * a local file path  -> copied (used by tests / offline dev)
  * a Google Drive link -> via drive.download (gdown)
  * any other https URL -> streamed with requests
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable, Optional

import requests

from . import drive

# Progress callback: (fraction_0_to_1) -> None
ProgressCb = Callable[[float], None]


def fetch(
    source: str,
    dest: str | Path,
    quiet: bool = True,
    progress: Optional[ProgressCb] = None,
) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    # Local file (testing / offline) — check before treating it as a URL.
    local = Path(source)
    if local.exists() and local.is_file():
        shutil.copyfile(local, dest)
        if progress:
            progress(1.0)
        return dest

    if drive.is_drive_url(source):
        return drive.download(source, dest, quiet=quiet, progress=progress)

    # Generic https download (use content-length for progress when available).
    with requests.get(source, stream=True, timeout=60) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 16):
                f.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(min(1.0, done / total))
    return dest
