"""Headless test of the safe-sync logic — no network, no GUI.

Run with:  python -m tests.test_sync   (from the project root)

Proves the two properties that matter:
  1. Mods we didn't install (Essential's jars, a friend's personal mod) survive.
  2. Re-syncing to a new version removes the OLD managed mods and never piles up
     two versions of the same jar.
"""

from __future__ import annotations

import io
import sys
import tempfile
import zipfile
from pathlib import Path

# Allow `python -m tests.test_sync` and `python tests/test_sync.py`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modupdater import sync  # noqa: E402


def make_zip(path: Path, jar_names: list[str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for name in jar_names:
            zf.writestr(name, b"fake jar bytes for " + name.encode())


def listing(mods_dir: Path) -> set[str]:
    return {p.name for p in mods_dir.iterdir()}


def run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        mods_dir = tmp / "mods"
        mods_dir.mkdir()

        # Simulate what's already in the folder after Essential's installer ran,
        # plus a personal mod the friend added themselves.
        (mods_dir / "Essential.jar").write_bytes(b"essential")
        (mods_dir / "fabric-api.jar").write_bytes(b"fabric")
        (mods_dir / "MyPersonalMod.jar").write_bytes(b"personal")

        # --- v1 sync ---
        z1 = tmp / "v1.zip"
        make_zip(z1, ["modA.jar", "modB.jar"])
        r1 = sync.sync_mods(mods_dir, z1, "1.21.1")
        assert set(r1["installed"]) == {"modA.jar", "modB.jar"}, r1
        assert r1["removed"] == [], r1
        now = listing(mods_dir)
        for keep in ("Essential.jar", "fabric-api.jar", "MyPersonalMod.jar"):
            assert keep in now, f"{keep} was wrongly deleted after v1"
        assert {"modA.jar", "modB.jar"} <= now
        assert sync.STATE_FILENAME in now

        # --- v2 sync: modA dropped, modB kept, modC added ---
        z2 = tmp / "v2.zip"
        make_zip(z2, ["modB.jar", "modC.jar"])
        r2 = sync.sync_mods(mods_dir, z2, "26.1.2")
        now = listing(mods_dir)
        assert "modA.jar" not in now, "old managed mod modA should have been removed"
        assert {"modB.jar", "modC.jar"} <= now
        # Untouched files still present:
        for keep in ("Essential.jar", "fabric-api.jar", "MyPersonalMod.jar"):
            assert keep in now, f"{keep} was wrongly deleted after v2"
        # No duplicate jars:
        jars = [p.name for p in mods_dir.iterdir() if p.suffix == ".jar"]
        assert len(jars) == len(set(jars)), f"duplicate jars: {jars}"

        # State reflects the latest version only.
        state = sync.read_state(mods_dir)
        assert state["version"] == "26.1.2", state
        assert set(state["managed"]) == {"modB.jar", "modC.jar"}, state

    print("PASS: safe-sync preserves untouched mods and never piles up versions.")

    # --- clean mode (fresh full install): wipe ALL jars first ---
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        mods_dir = tmp / "mods"
        mods_dir.mkdir()
        # Essential's installer left a jar under a *different* filename than the
        # one bundled in the zip — the duplicate-Essential trap.
        (mods_dir / "Essential.jar").write_bytes(b"installer-essential")
        (mods_dir / "leftover.jar").write_bytes(b"junk")

        z = tmp / "pack.zip"
        make_zip(z, ["Essential-1.3.10.9.jar", "fabric-api.jar", "sodium.jar"])
        sync.sync_mods(mods_dir, z, "26.1.2", clean=True)
        now = listing(mods_dir)
        assert "Essential.jar" not in now, "clean install should remove installer's jar"
        assert "leftover.jar" not in now, "clean install should wipe all old jars"
        assert {"Essential-1.3.10.9.jar", "fabric-api.jar", "sodium.jar"} <= now
        jars = [n for n in now if n.endswith(".jar")]
        assert len(jars) == 3, f"expected exactly the 3 zip jars, got {jars}"
    print("PASS: clean install wipes old jars and avoids duplicate Essential.")

    # --- clean mode when the pack does NOT bundle Essential ---
    # The installer's Essential jar must be preserved (else Essential goes missing).
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        mods_dir = tmp / "mods"
        mods_dir.mkdir()
        (mods_dir / "Essential-1.3.10.9.jar").write_bytes(b"installer-essential")
        (mods_dir / "old-pack-mod.jar").write_bytes(b"junk")

        z = tmp / "pack.zip"
        make_zip(z, ["fabric-api.jar", "sodium.jar"])  # no Essential in the pack
        sync.sync_mods(mods_dir, z, "1.21.10", clean=True)
        now = listing(mods_dir)
        assert "Essential-1.3.10.9.jar" in now, "Essential must be kept when pack lacks it"
        assert "old-pack-mod.jar" not in now, "other old jars should still be wiped"
        assert {"fabric-api.jar", "sodium.jar"} <= now
        ess = [n for n in now if n.lower().startswith("essential")]
        assert len(ess) == 1, f"exactly one Essential expected, got {ess}"
    print("PASS: clean install keeps installer's Essential when the pack omits it.")


if __name__ == "__main__":
    run()
