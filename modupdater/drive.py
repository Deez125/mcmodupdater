"""Download a single shared file from Google Drive.

We only ever fetch *specific* files by their share link (the manifest, and each
version's mods.zip) — never list a folder — because gdown handles the per-file
download (including the big-file virus-scan confirmation) reliably, whereas
scraping folder contents does not.

gdown 6.x takes the file *id* (not a full share URL), so we pull the id out of
whatever share-link format the user pasted.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional

import gdown

# Progress callback: (fraction_0_to_1) -> None
ProgressCb = Callable[[float], None]


def is_drive_url(url: str) -> bool:
    return "drive.google.com" in url or "docs.google.com" in url


def extract_file_id(url: str) -> str:
    """Pull the Drive file id out of any common share-link shape (or a bare id)."""
    m = re.search(r"/d/([A-Za-z0-9_-]+)", url) or re.search(
        r"[?&]id=([A-Za-z0-9_-]+)", url
    )
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", url):  # someone pasted just the id
        return url
    raise ValueError(f"Couldn't find a Google Drive file id in: {url}")


def download(
    url: str,
    dest: str | Path,
    quiet: bool = True,
    progress: Optional[ProgressCb] = None,
) -> Path:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    file_id = extract_file_id(url)

    kwargs = {}
    if progress is not None:
        # gdown calls back with (current_bytes, total_bytes_or_None).
        def _gdown_progress(current: int, total: Optional[int]) -> None:
            if total:
                progress(min(1.0, current / total))

        kwargs["progress"] = _gdown_progress

    out = gdown.download(id=file_id, output=str(dest), quiet=quiet, **kwargs)
    if not out:
        raise RuntimeError(
            "Google Drive download failed. Is the file shared as "
            "'Anyone with the link'?"
        )
    return Path(out)
