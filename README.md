# MC Mod Updater

A dead-simple tool so a friend group can keep their Minecraft (Fabric + Essential)
modpack in sync. One person maintains the mods; everyone else clicks a button.

## What it does

- **Update My Mods** *(working)* — reads the version list, downloads that version's
  `mods.zip` from Google Drive, and syncs it into your Essential install's mods
  folder. It only ever touches mods *it* installed (tracked in a tiny
  `.modsync.json`), so Essential's own jars and any mods you added yourself are
  left alone — and you never end up with two versions of the same mod.
- **Full Install (set up from scratch)** *(coming next)* — will run Essential's
  installer, guide you through the few clicks, then install all the mods.

## How updates work (for the maintainer)

You never recompile the `.exe`. To publish a new version:

1. Zip that version's mods into a `mods.zip` and upload it to Google Drive
   (shared "Anyone with the link").
2. Add one line to `manifest.json` mapping the version to that zip's share link,
   and re-upload it. See [`sample_manifest.json`](sample_manifest.json) for the shape.

The only thing baked into the build is `MANIFEST_URL` in
[`modupdater/config.py`](modupdater/config.py) — the share link to that manifest.
Set it once. (For local development, if `MANIFEST_URL` is still the placeholder,
the app automatically uses a `manifest.json` file sitting next to it — see the
checked-in [`manifest.json`](manifest.json) — so you can test before uploading
anything to Drive.)

**The `mods.zip` is the complete mod set** — it includes Essential and Fabric API
themselves, not just the extras. The Full Install path accounts for this: it wipes
the mods folder before laying down the zip, so the installer's bundled Essential
jar can't collide with the zip's copy. (The quick-update path leaves any mods you
added yourself alone.)

## Run from source (dev)

```sh
python -m pip install -r requirements.txt
python run.py
```

## Test the sync logic (no network, no GUI)

```sh
python -m tests.test_sync
```

## Build the .exe

```sh
build.bat
```

The result lands in `dist\MC Mod Updater.exe`.

## Layout

| Path | Purpose |
| --- | --- |
| `modupdater/config.py` | The one setting to fill in (`MANIFEST_URL`). |
| `modupdater/manifest.py` | Loads/validates the version index. |
| `modupdater/drive.py` / `resources.py` | Downloading (Drive / https / local). |
| `modupdater/minecraft.py` | Finds `.minecraft`, installations, mods folders. |
| `modupdater/sync.py` | Safe mod sync via `.modsync.json`. |
| `modupdater/gui/app.py` | The CustomTkinter wizard. |
| `tests/test_sync.py` | Headless proof the sync is safe. |
