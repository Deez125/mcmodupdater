"""Read a version's mods from the GitHub folders described in the manifest's
`source` block.

Everything the app needs to build URLs lives in that block, so nothing about the
repo/branch/paths is hardcoded here — change the manifest and this follows.

Folder layout (per the source templates):
    mods/<version>/required/         all installed, always
    mods/<version>/optional/         installed only if the user ticks them
    mods/<version>/optional/images/  one preview image per optional mod

Jars are matched to manifest entries by a case-insensitive name *prefix* (the
`jar` field), so bumping a mod's version — which changes its filename — never
needs a manifest edit; you just replace the file in the folder.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import requests


class ModSourceError(Exception):
    """Raised when the GitHub folders can't be read."""


class ModSource:
    def __init__(self, source: dict) -> None:
        self.raw_base = source["raw_base"]
        self.api_base = source["api_base"]
        self.branch = source["branch"]
        self.required_dir = source["required_dir"]
        self.optional_dir = source["optional_dir"]
        self.images_dir = source["images_dir"]

    # ---- low-level ----
    def _dir(self, template: str, version: str) -> str:
        return template.replace("{version}", version)

    def _list_files(self, path: str) -> List[dict]:
        url = f"{self.api_base}{path}?ref={self.branch}"
        try:
            r = requests.get(url, timeout=30)
        except requests.RequestException as e:
            raise ModSourceError(f"Couldn't reach GitHub: {e}") from e
        if r.status_code == 404:
            raise ModSourceError(f"Folder not found on GitHub: {path}")
        if r.status_code == 403 and "rate limit" in r.text.lower():
            raise ModSourceError(
                "GitHub rate limit hit — please wait a few minutes and try again."
            )
        if not r.ok:
            raise ModSourceError(f"GitHub returned {r.status_code} for {path}")
        return [f for f in r.json() if f.get("type") == "file"]

    def _jars(self, path: str) -> Dict[str, str]:
        """{filename: download_url} for every .jar directly in `path`."""
        return {
            f["name"]: f["download_url"]
            for f in self._list_files(path)
            if f["name"].lower().endswith(".jar")
        }

    # ---- public ----
    def image_url(self, version: str, image: str) -> str:
        return f"{self.raw_base}{self._dir(self.images_dir, version)}/{image}"

    def required_jars(self, version: str) -> Dict[str, str]:
        """Every jar in required/ — all of these get installed."""
        return self._jars(self._dir(self.required_dir, version))

    def resolve_optional(self, version: str, mods: List[dict]) -> List[dict]:
        """Pair each manifest optional mod with its actual jar + image.

        Returns a copy of each mod dict plus:
          filename     — the real jar name in the folder (or None if missing)
          download_url — where to fetch the jar (None if missing)
          image_url    — full raw URL to its preview image
          available    — True if a jar was found (or an explicit `url` is set)
        """
        index = self._jars(self._dir(self.optional_dir, version))
        out: List[dict] = []
        for m in mods:
            entry = dict(m)
            entry["image_url"] = self.image_url(version, m["image"])
            entry["inactive"] = bool(m.get("inactive"))
            if entry["inactive"]:
                # Intentionally shown but not installable (e.g. too big to host).
                entry["filename"] = None
                entry["download_url"] = None
                entry["available"] = False
                out.append(entry)
                continue
            url_override = m.get("url")
            if url_override:
                entry["filename"] = url_override.rsplit("/", 1)[-1]
                entry["download_url"] = url_override
                entry["available"] = True
            else:
                prefix = m.get("jar", "").lower()
                match = next(
                    (name for name in index if name.lower().startswith(prefix)), None
                ) if prefix else None
                entry["filename"] = match
                entry["download_url"] = index.get(match) if match else None
                entry["available"] = match is not None
            out.append(entry)
        return out
