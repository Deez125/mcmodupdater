"""Safely sync mods into a folder without clobbering anything we didn't put there.

Strategy: we drop a small `.modsync.json` in the mods folder recording exactly
which jars WE installed. On the next run we delete only those, then install the
new set. That means:
  * Essential's own jars (Essential, Fabric API) are never touched.
  * A friend's personally-added mod is never deleted.
  * No two versions of the same mod can pile up.
"""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List

STATE_FILENAME = ".modsync.json"


def state_path(mods_dir: Path) -> Path:
    return Path(mods_dir) / STATE_FILENAME


def read_state(mods_dir: Path) -> dict:
    p = state_path(mods_dir)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def write_state(mods_dir: Path, version: str, managed: List[str]) -> None:
    data = {
        "version": version,
        "managed": sorted(managed),
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    state_path(mods_dir).write_text(json.dumps(data, indent=2), encoding="utf-8")


def _zip_jar_names(zip_path: Path) -> set[str]:
    """Basenames of every .jar inside the zip (without extracting)."""
    with zipfile.ZipFile(zip_path) as zf:
        return {Path(n).name for n in zf.namelist() if n.lower().endswith(".jar")}


def _is_essential_jar(name: str) -> bool:
    return name.lower().startswith("essential")


def _extract_jars(zip_path: Path, out_dir: Path) -> List[str]:
    """Pull every .jar out of the zip (flattening any internal folders)."""
    names: List[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            name = Path(info.filename).name
            if not name.lower().endswith(".jar"):
                continue
            with zf.open(info) as src, open(out_dir / name, "wb") as dst:
                shutil.copyfileobj(src, dst)
            names.append(name)
    return names


def _remove_before_install(
    mods_dir: Path, clean: bool, incoming_names, log: Callable[[str], None]
) -> List[str]:
    """Remove the right jars before laying down new ones, returning what was removed.

    clean=False (update): remove only the jars WE installed last time (per
    .modsync.json), leaving Essential's jars and personal mods alone.
    clean=True (fresh install): wipe all jars, but keep the installer's Essential
    jar when the incoming set doesn't include its own copy.
    """
    removed: List[str] = []
    if clean:
        incoming_has_essential = any(_is_essential_jar(n) for n in incoming_names)
        for f in mods_dir.glob("*.jar"):
            if _is_essential_jar(f.name) and not incoming_has_essential:
                log(f"Keeping {f.name} (Essential — not included in this pack).")
                continue
            f.unlink()
            removed.append(f.name)
        if removed:
            log(f"Cleared {len(removed)} existing mod(s) for a fresh install.")
    else:
        for name in read_state(mods_dir).get("managed", []):
            f = mods_dir / name
            if f.exists():
                f.unlink()
                removed.append(name)
        if removed:
            log(f"Removed {len(removed)} old mod(s) from the previous sync.")
    return removed


def install_jars(
    mods_dir: str | Path,
    jar_sources: Dict[str, str],
    version: str,
    log: Callable[[str], None] = lambda _msg: None,
    progress: Callable[[float], None] = lambda _frac: None,
    clean: bool = False,
    fetch: Callable[[str, Path], object] | None = None,
) -> Dict[str, List[str]]:
    """Install a chosen set of jars into `mods_dir` from individual URLs.

    `jar_sources` maps each jar's filename -> its download URL (required mods plus
    whatever optional mods the user picked). Same safe-sync semantics as
    `sync_mods`: only our managed jars are replaced, Essential is preserved.

    `fetch` is injectable for testing; defaults to resources.fetch.
    """
    mods_dir = Path(mods_dir)
    mods_dir.mkdir(parents=True, exist_ok=True)
    if not jar_sources:
        raise RuntimeError("No mods to install.")
    if fetch is None:
        from . import resources
        fetch = resources.fetch

    names = list(jar_sources)
    removed = _remove_before_install(mods_dir, clean, names, log)

    # Download every jar to a temp dir first, so a failed download can't leave the
    # mods folder half-written.
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        total = len(jar_sources)
        for i, (name, url) in enumerate(jar_sources.items(), start=1):
            log(f"Downloading {name}…")
            fetch(url, tmp / name)
            progress(i / total)
        for name in names:
            shutil.copyfile(tmp / name, mods_dir / name)

    write_state(mods_dir, version, names)
    log(f"Done — {len(names)} mod(s) installed in {mods_dir}")
    return {"installed": names, "removed": removed}


def sync_mods(
    mods_dir: str | Path,
    zip_path: str | Path,
    version: str,
    log: Callable[[str], None] = lambda _msg: None,
    progress: Callable[[float], None] = lambda _frac: None,
    clean: bool = False,
) -> Dict[str, List[str]]:
    """Install the mods from `zip_path` into `mods_dir`.

    `progress` is called with a 0.0–1.0 fraction as mods are installed, for a
    determinate progress bar.

    `clean=False` (update): remove only the mods WE installed last time, leaving
    Essential's own jars and any personal mods alone.
    `clean=True` (fresh full install): remove existing .jar files first so the
    installer's bundled Essential jar can't collide with the zip's copy. Safe
    because a fresh install has nothing personal to preserve. EXCEPTION: if the
    pack doesn't ship its own Essential jar (some versions bundle it, some rely on
    the installer's copy), the installer's Essential jar is kept so Essential isn't
    left missing.

    Returns {"installed": [...], "removed": [...]}.
    """
    mods_dir = Path(mods_dir)
    zip_path = Path(zip_path)
    mods_dir.mkdir(parents=True, exist_ok=True)

    # 1. Decide what to remove before installing.
    removed = _remove_before_install(
        mods_dir, clean, _zip_jar_names(zip_path) if clean else [], log
    )

    # 2. Extract the new jars to a temp dir first (so a bad zip can't half-wreck
    #    the mods folder).
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        jars = _extract_jars(zip_path, tmp)
        if not jars:
            raise RuntimeError("No .jar files were found inside the mods zip.")
        log(f"Installing {len(jars)} mod(s)...")
        for i, name in enumerate(jars, start=1):
            shutil.copyfile(tmp / name, mods_dir / name)
            progress(i / len(jars))

    # 3. Record what we installed for next time.
    write_state(mods_dir, version, jars)
    log(f"Done — {len(jars)} mod(s) ready in {mods_dir}")
    return {"installed": jars, "removed": removed}
