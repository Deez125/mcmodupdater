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

You never recompile the `.exe`. To publish a new game version:

1. Zip that version's mods into a `mods.zip` and upload it to Google Drive
   (shared "Anyone with the link").
2. Add a version entry to [`manifest.json`](manifest.json) and `git push`:
   ```json
   "1.21.11": { "mods_zip": "https://drive.google.com/file/d/NEW_FILE_ID/view" }
   ```
   The app reads the manifest live from this repo, so the new version appears in
   everyone's dropdown within a few minutes — no rebuild.

The only thing baked into the build is `MANIFEST_URL` in
[`modupdater/config.py`](modupdater/config.py) — the raw link to `manifest.json`
in this repo. Set once, never touched again.

**Essential comes from its own installer, not the packs.** The Full Install path
runs Essential's installer (which drops `Essential.jar` into the mods folder),
then installs the pack. When it wipes the folder for a fresh install, it keeps the
installer's Essential jar if the pack doesn't ship one. The quick-update path only
swaps the mods it manages, leaving Essential — and any mods you added yourself —
untouched.

## Run from source (dev)

```sh
python -m pip install -r requirements.txt
python run.py
```

## Build the .exe

```sh
build.bat
```

The result lands in `dist\MCModUpdater.exe`, distributed via GitHub Releases.

## Layout

| Path | Purpose |
| --- | --- |
| `modupdater/config.py` | The one setting to fill in (`MANIFEST_URL`). |
| `modupdater/manifest.py` | Loads/validates the version index. |
| `modupdater/drive.py` / `resources.py` | Downloading (Drive / https / local). |
| `modupdater/minecraft.py` | Finds `.minecraft`, installations, mods folders. |
| `modupdater/sync.py` | Safe mod sync via `.modsync.json`. |
| `modupdater/gui/app.py` | The CustomTkinter wizard. |
