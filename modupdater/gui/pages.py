"""Wizard pages: Welcome -> Version -> [Essential] -> Sync -> Done.

Each page is a CTkFrame. The shared WizardApp (self.wiz) carries state between
them and runs slow work off-thread. Pages keep UI updates on the main thread via
self._safe(...).
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from .. import (
    config,
    essential,
    manifest,
    minecraft,
    resources,
    sync,
    version_utils,
)

MUTED = ("gray40", "gray70")
GOOD = ("#1a7f37", "#7CFC8C")
BAD = ("#B00020", "salmon")
WARN = ("#9a6700", "#E3B341")


# --------------------------------------------------------------------------- #
# Base page + small shared widgets
# --------------------------------------------------------------------------- #
class Page(ctk.CTkFrame):
    def __init__(self, wiz) -> None:
        super().__init__(wiz.container, fg_color="transparent")
        self.wiz = wiz

    def on_show(self) -> None:  # called after the page is packed
        pass

    def on_hide(self) -> None:  # called right before the page is destroyed
        pass

    def _safe(self, fn) -> None:
        """Schedule `fn` on the UI thread; no-op if the page is already gone."""
        def wrapped() -> None:
            try:
                if self.winfo_exists():
                    fn()
            except Exception:
                pass
        self.wiz.after(0, wrapped)


def title_block(parent, title: str, subtitle: str | None = None) -> None:
    ctk.CTkLabel(
        parent, text=title, font=ctk.CTkFont(size=24, weight="bold")
    ).pack(pady=(36, 6))
    if subtitle:
        ctk.CTkLabel(
            parent, text=subtitle, text_color=MUTED, wraplength=520, justify="center"
        ).pack(pady=(0, 18))


def big_choice_button(parent, title: str, command) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent,
        text=title,
        command=command,
        height=56,
        font=ctk.CTkFont(size=16, weight="bold"),
        anchor="center",
    )


# --------------------------------------------------------------------------- #
# 1. Welcome  (also loads the manifest)
# --------------------------------------------------------------------------- #
class WelcomePage(Page):
    def on_show(self) -> None:
        self._build_branding()
        ctk.CTkLabel(
            self, text=config.SERVER_NAME, font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=(2, 22))

        self.btn_full = big_choice_button(
            self, "Set up a modded install", self._choose_full
        )
        self.btn_full.pack(fill="x", padx=48, pady=(4, 10))

        self.btn_update = big_choice_button(
            self, "Just update my mods", self._choose_update
        )
        self.btn_update.pack(fill="x", padx=48, pady=(0, 18))

        self.status = ctk.CTkLabel(self, text="", text_color=MUTED, wraplength=520)
        self.status.pack(pady=(4, 6))
        self.bar = ctk.CTkProgressBar(self, width=360)
        self.bar.pack(pady=(0, 8))
        self.bar.set(0)
        self.retry_btn = ctk.CTkButton(self, text="Try again", command=self._load_manifest)

        if self.wiz.ctx.get("manifest"):
            self._enable_choices()
        else:
            self._load_manifest()

    def _build_branding(self) -> None:
        """Show the server's icon at the top. Cosmetic — never blocks the wizard."""
        path = config.icon_path()
        if path is None:
            return
        try:
            from PIL import Image

            pil = Image.open(path)
            h = 120
            w = max(1, round(pil.width * (h / pil.height)))
            # Keep a reference on self so Tk doesn't garbage-collect the image.
            self._brand_img = ctk.CTkImage(light_image=pil, dark_image=pil, size=(w, h))
            ctk.CTkLabel(self, image=self._brand_img, text="").pack(pady=(24, 6))
        except Exception:
            pass

    def _set_choices_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        self.btn_full.configure(state=state)
        self.btn_update.configure(state=state)

    def _enable_choices(self) -> None:
        self._set_choices_enabled(True)
        self.bar.pack_forget()
        self.status.configure(text="")

    def _load_manifest(self) -> None:
        self._set_choices_enabled(False)
        self.retry_btn.pack_forget()
        self.bar.pack(pady=(0, 8))
        self.bar.configure(mode="indeterminate")
        self.bar.start()
        self.status.configure(text="Loading the version list…", text_color=MUTED)

        def work() -> None:
            data = manifest.fetch_manifest()
            self._safe(lambda: self._on_loaded(data))

        self.wiz.run_async(work, on_error=lambda e: self._safe(lambda: self._on_error(e)))

    def _on_loaded(self, data: dict) -> None:
        self.wiz.ctx["manifest"] = data
        self.bar.stop()
        n = len(manifest.version_names(data))
        self.status.configure(text=f"Ready. {n} version(s) available.", text_color=GOOD)
        self._enable_choices()

    def _on_error(self, e: Exception) -> None:
        self.bar.stop()
        self.bar.pack_forget()
        msg = str(e)
        self.status.configure(
            text=f"Couldn't load the version list:\n{msg}", text_color=BAD
        )
        self.retry_btn.pack(pady=(2, 6))

    def _choose_full(self) -> None:
        self.wiz.ctx["mode"] = "full"
        self.wiz.show_page(VersionPage)

    def _choose_update(self) -> None:
        self.wiz.ctx["mode"] = "update"
        self.wiz.show_page(VersionPage)


# --------------------------------------------------------------------------- #
# 2. Version selection
# --------------------------------------------------------------------------- #
class VersionPage(Page):
    def on_show(self) -> None:
        title_block(
            self,
            "Choose your Minecraft version",
            "The newest is picked for you. Only change it if the server is on an "
            "older version.",
        )
        data = self.wiz.ctx["manifest"]
        versions = version_utils.sort_desc(manifest.version_names(data))
        current = self.wiz.ctx.get("version") or versions[0]

        self.menu = ctk.CTkOptionMenu(
            self, values=versions, width=240, height=40,
            font=ctk.CTkFont(size=15),
        )
        self.menu.set(current)
        self.menu.pack(pady=(6, 26))

        ctk.CTkButton(
            self, text="Continue →", height=46, width=240,
            font=ctk.CTkFont(size=15, weight="bold"), command=self._continue,
        ).pack(pady=(0, 8))
        ctk.CTkButton(
            self, text="← Back", height=34, width=140, fg_color="gray30",
            hover_color="gray25", command=lambda: self.wiz.show_page(WelcomePage),
        ).pack()

    def _continue(self) -> None:
        self.wiz.ctx["version"] = self.menu.get()
        # These are version/run-specific; clear so a new run can't reuse them.
        self.wiz.ctx["mods_dir"] = None
        self.wiz.ctx["install_name"] = None
        self.wiz.ctx["installer_file"] = None
        if self.wiz.ctx["mode"] == "full":
            self.wiz.show_page(EssentialPage)
        else:
            self.wiz.show_page(SyncPage)


# --------------------------------------------------------------------------- #
# 3. Essential install (full-install mode only)
# --------------------------------------------------------------------------- #
class EssentialPage(Page):
    POLL_MS = 1500

    def on_show(self) -> None:
        self._stopped = False
        version = self.wiz.ctx["version"]
        existing = essential.find_ready_installation(version)
        if existing is not None:
            # Already installed: skip Essential, but warn that we're about to wipe.
            self._build_existing_warning(version, existing)
        else:
            self._build_installer_flow(version)

    def on_hide(self) -> None:
        self._stopped = True

    # -- existing-install warning --
    def _build_existing_warning(self, version: str, install_path) -> None:
        self.wiz.ctx["mods_dir"] = minecraft.mods_dir_for(install_path)
        self.wiz.ctx["install_name"] = install_path.name

        title_block(self, "Essential is already installed")
        ctk.CTkLabel(
            self,
            text=f"You already have a “{install_path.name}” install, so we'll skip "
            "installing Essential and go straight to the mods.",
            font=ctk.CTkFont(size=15), wraplength=560, justify="center",
        ).pack(padx=40, pady=(0, 12))

        ctk.CTkLabel(
            self,
            text="⚠  Heads up: continuing will REMOVE every mod currently in that "
            f"folder and replace it with the server's {version} pack. Any mods you "
            "added yourself will be wiped.",
            text_color=WARN, font=ctk.CTkFont(size=14, weight="bold"),
            wraplength=560, justify="center",
        ).pack(padx=40, pady=(0, 8))

        ctk.CTkLabel(
            self, text=str(minecraft.mods_dir_for(install_path)),
            text_color=MUTED, wraplength=560, justify="center",
        ).pack(padx=40, pady=(0, 16))

        ctk.CTkButton(
            self, text="📂  Open that mods folder", width=240, height=40,
            fg_color="gray30", hover_color="gray25", command=self._open_mods_folder,
        ).pack(pady=(0, 18))
        ctk.CTkButton(
            self, text="Continue — wipe & install mods", width=300, height=46,
            font=ctk.CTkFont(size=15, weight="bold"), command=self._advance,
        ).pack(pady=(0, 8))
        ctk.CTkButton(
            self, text="← Back", height=32, width=130, fg_color="gray30",
            hover_color="gray25", command=lambda: self.wiz.show_page(VersionPage),
        ).pack()

    def _open_mods_folder(self) -> None:
        mods_dir = self.wiz.ctx.get("mods_dir")
        if mods_dir:
            minecraft.open_in_explorer(mods_dir)

    # -- fresh-install flow --
    def _build_installer_flow(self, version: str) -> None:
        self._installer_path = None
        title_block(self, "Step 1 of 2 · Install Essential")

        instructions = (
            f"In the Essential installer that opens:\n\n"
            f"   1.  Select  Minecraft Launcher\n"
            f"   2.  Click  New Installation\n"
            f"   3.  Leave the name as  “{version} Fabric Essential”,\n"
            f"        choose  {version}  in the version dropdown,\n"
            f"        confirm  Fabric  is the selected mod loader,\n"
            f"        then click  Create and Install Essential\n"
            f"   4.  When it finishes, close the Essential installer\n\n"
            f"The wizard continues automatically once it's done."
        )
        ctk.CTkLabel(
            self, text=instructions, justify="left", font=ctk.CTkFont(size=14),
        ).pack(padx=40, pady=(0, 14), anchor="w")

        self.status = ctk.CTkLabel(self, text="", text_color=MUTED, wraplength=560)
        self.status.pack(pady=(0, 4))
        self.bar = ctk.CTkProgressBar(self, width=380)
        self.bar.set(0)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.pack(pady=(16, 6))
        self.relaunch_btn = ctk.CTkButton(
            btns, text="Open installer again", width=180, command=self._relaunch,
        )
        self.relaunch_btn.grid(row=0, column=0, padx=6)
        ctk.CTkButton(
            btns, text="I've finished — continue", width=200,
            command=self._manual_continue,
        ).grid(row=0, column=1, padx=6)
        ctk.CTkButton(
            self, text="← Back", height=32, width=130, fg_color="gray30",
            hover_color="gray25", command=lambda: self.wiz.show_page(VersionPage),
        ).pack(pady=(6, 0))

        self._start_installer()
        self._poll()

    # -- installer download/launch --
    def _start_installer(self) -> None:
        url = manifest.essential_installer_url(self.wiz.ctx["manifest"])
        if not url:
            self._fallback_to_browser(
                "No direct installer link is set, so I opened essential.gg."
            )
            return

        self.bar.pack(pady=(2, 6))
        self.bar.configure(mode="determinate")
        self.bar.set(0)
        self.status.configure(
            text="Downloading the Essential installer to your Downloads folder…",
            text_color=MUTED,
        )

        def work() -> None:
            path = essential.download_installer(url, progress=self._set_bar)
            essential.launch(path)
            self._safe(lambda: self._installer_launched(path))

        self.wiz.run_async(work, on_error=lambda e: self._safe(lambda: self._dl_failed(e)))

    def _set_bar(self, frac: float) -> None:
        self._safe(lambda: (self.bar.configure(mode="determinate"), self.bar.set(frac)))

    def _installer_launched(self, path) -> None:
        self.wiz.ctx["installer_file"] = str(path)
        self.bar.stop()
        self.bar.pack_forget()
        self.status.configure(
            text=f"Downloaded {path.name} and opened it. Follow the 3 steps above — "
            "this wizard continues automatically when the install finishes.",
            text_color=GOOD,
        )

    def _dl_failed(self, e: Exception) -> None:
        self.bar.stop()
        self.bar.pack_forget()
        self._fallback_to_browser(f"Couldn't auto-download the installer ({e}).")

    def _fallback_to_browser(self, why: str) -> None:
        """Open essential.gg and watch Downloads — auto-launch the installer when
        the user grabs it via the browser."""
        self._dl_snapshot = essential.list_installers()
        essential.open_website()
        self.status.configure(
            text=f"{why} Please download the installer there — I'll open it for you "
            "automatically once it lands in your Downloads folder.",
            text_color=MUTED,
        )
        self._poll_downloads()

    def _poll_downloads(self) -> None:
        if self._stopped or not self.winfo_exists():
            return
        found = essential.find_new_installer(getattr(self, "_dl_snapshot", set()))
        if found is not None:
            self.wiz.ctx["installer_file"] = str(found)
            essential.launch(found)
            self.status.configure(
                text=f"Found {found.name} in Downloads and opened it. Follow the 3 "
                "steps above.",
                text_color=GOOD,
            )
            return
        self.after(self.POLL_MS, self._poll_downloads)

    def _relaunch(self) -> None:
        self.status.configure(text="Re-opening the installer…", text_color=MUTED)
        self._start_installer()

    # -- watch for completion --
    def _poll(self) -> None:
        if self._stopped or not self.winfo_exists():
            return
        version = self.wiz.ctx["version"]
        if essential.find_ready_installation(version):
            self.status.configure(text="Essential install detected!", text_color=GOOD)
            self._advance()
            return
        self.after(self.POLL_MS, self._poll)

    def _manual_continue(self) -> None:
        self._advance()

    def _advance(self) -> None:
        self._stopped = True
        version = self.wiz.ctx["version"]
        inst = essential.find_ready_installation(version)
        if inst:
            self.wiz.ctx["mods_dir"] = minecraft.mods_dir_for(inst)
            self.wiz.ctx["install_name"] = inst.name
        self.wiz.show_page(SyncPage)


# --------------------------------------------------------------------------- #
# 4. Download + sync mods
# --------------------------------------------------------------------------- #
class SyncPage(Page):
    def on_show(self) -> None:
        step = "Step 2 of 2 · " if self.wiz.ctx["mode"] == "full" else ""
        title_block(self, f"{step}Installing mods")

        self.status = ctk.CTkLabel(self, text="", text_color=MUTED, wraplength=560)
        self.status.pack(pady=(0, 6))
        self.bar = ctk.CTkProgressBar(self, width=420)
        self.bar.set(0)
        self.bar.pack(pady=(2, 10))

        self.log_box = ctk.CTkTextbox(self, height=170)
        self.log_box.pack(fill="both", expand=True, padx=30, pady=(4, 12))
        self.log_box.configure(state="disabled")

        self.action = ctk.CTkButton(self, text="", command=lambda: None)
        self.back = ctk.CTkButton(
            self, text="← Back", height=32, width=130, fg_color="gray30",
            hover_color="gray25", command=self._go_back,
        )

        mods_dir = self._resolve_mods_dir()
        if mods_dir is None:
            self._prompt_browse()
        else:
            self.wiz.ctx["mods_dir"] = mods_dir
            self._start()

    def _go_back(self) -> None:
        target = EssentialPage if self.wiz.ctx["mode"] == "full" else VersionPage
        self.wiz.show_page(target)

    def _resolve_mods_dir(self) -> Path | None:
        if self.wiz.ctx.get("mods_dir"):
            return Path(self.wiz.ctx["mods_dir"])
        version = self.wiz.ctx["version"]
        inst = minecraft.find_installation_for_version(version)
        if inst:
            self.wiz.ctx["install_name"] = inst.name
            return minecraft.mods_dir_for(inst)
        return None

    def _prompt_browse(self) -> None:
        version = self.wiz.ctx["version"]
        self.status.configure(
            text=f"Couldn't find the '{minecraft.expected_install_name(version)}' "
            "install automatically. Point me at your mods folder:",
            text_color=BAD,
        )
        self.bar.pack_forget()
        self.action.configure(text="Choose mods folder…", command=self._browse)
        self.action.pack(pady=(2, 6))
        self.back.pack(pady=(2, 8))

    def _browse(self) -> None:
        start = minecraft.installations_dir()
        chosen = filedialog.askdirectory(
            title="Select your mods folder",
            initialdir=str(start if start.exists() else Path.home()),
        )
        if chosen:
            self.wiz.ctx["mods_dir"] = Path(chosen)
            self.wiz.ctx["install_name"] = Path(chosen).parent.name
            self.action.pack_forget()
            self.back.pack_forget()
            self.bar.pack(pady=(2, 10))
            self._start()

    # -- logging --
    def _log(self, msg: str) -> None:
        def append() -> None:
            self.log_box.configure(state="normal")
            self.log_box.insert("end", msg + "\n")
            self.log_box.see("end")
            self.log_box.configure(state="disabled")
        self._safe(append)

    def _set_progress(self, frac: float) -> None:
        self._safe(lambda: (self.bar.configure(mode="determinate"), self.bar.set(frac)))

    # -- the work --
    def _start(self) -> None:
        version = self.wiz.ctx["version"]
        mods_dir = Path(self.wiz.ctx["mods_dir"])
        self._safe(lambda: self.status.configure(
            text=f"Installing mods for {version}…", text_color=MUTED))
        self._safe(lambda: (self.bar.configure(mode="indeterminate"), self.bar.start()))

        clean = self.wiz.ctx["mode"] == "full"

        def work() -> None:
            data = self.wiz.ctx["manifest"]
            url = manifest.mods_zip_url(data, version)
            self._log("Downloading mods… (this can take a minute on a big pack)")
            tmp_zip = Path(tempfile.gettempdir()) / f"mcmodupdater_mods_{version}.zip"
            self._safe(lambda: (self.bar.stop(), self.bar.configure(mode="determinate"),
                                self.bar.set(0)))
            resources.fetch(url, tmp_zip, progress=self._set_progress)
            self._log("Download complete. Syncing…")
            self._safe(lambda: self.bar.set(0))
            result = sync.sync_mods(
                mods_dir, tmp_zip, version, log=self._log,
                progress=self._set_progress, clean=clean,
            )
            self._safe(lambda: self._done(result))

        self.wiz.run_async(work, on_error=lambda e: self._safe(lambda: self._failed(e)))

    def _done(self, result: dict) -> None:
        self.bar.stop()
        self.bar.set(1)
        self.wiz.ctx["installed_count"] = len(result["installed"])
        self.wiz.show_page(DonePage)

    def _failed(self, e: Exception) -> None:
        self.bar.stop()
        self.bar.set(0)
        self.status.configure(text=f"Something went wrong: {e}", text_color=BAD)
        self._log(f"ERROR: {e}")
        self.action.configure(text="Try again", command=self._start)
        self.action.pack(pady=(2, 6))
        self.back.pack(pady=(2, 8))


# --------------------------------------------------------------------------- #
# 5. Done
# --------------------------------------------------------------------------- #
class DonePage(Page):
    def on_show(self) -> None:
        title_block(self, "All done!  🎉")
        count = self.wiz.ctx.get("installed_count")
        name = self.wiz.ctx.get("install_name")
        lines = []
        if count is not None:
            lines.append(f"{count} mod(s) installed.")
        lines.append("In the Minecraft launcher" + (
            f", pick the “{name}” installation" if name else "") + " and hit Play.")
        ctk.CTkLabel(
            self, text="\n".join(lines), font=ctk.CTkFont(size=15),
            wraplength=520, justify="center",
        ).pack(pady=(4, 24))

        ctk.CTkButton(
            self, text="🎮  Launch Minecraft", height=48, width=240,
            font=ctk.CTkFont(size=16, weight="bold"), command=self._launch,
        ).pack(pady=(0, 14))

        self.status = ctk.CTkLabel(self, text="", text_color=MUTED, wraplength=520)
        self.status.pack(pady=(0, 8))

        self._build_installer_reminder()

        ctk.CTkButton(
            self, text="Update again", height=38, width=200, fg_color="gray30",
            hover_color="gray25", command=self._again,
        ).pack(pady=(0, 6))
        ctk.CTkButton(
            self, text="Close", height=34, width=160, fg_color="gray30",
            hover_color="gray25", command=self.wiz.destroy,
        ).pack()

    def _launch(self) -> None:
        if minecraft.launch_minecraft():
            self.status.configure(text="Opening the Minecraft launcher…", text_color=GOOD)
        else:
            self.status.configure(
                text="Couldn't find the Minecraft launcher automatically — open it "
                "yourself from the Start menu.",
                text_color=BAD,
            )

    # -- leftover Essential installer cleanup --
    def _build_installer_reminder(self) -> None:
        """If we downloaded the Essential installer this run and it's still in
        Downloads, remind the user to delete it (with a one-click option)."""
        installer = self.wiz.ctx.get("installer_file")
        if not installer or not Path(installer).exists():
            return
        self._installer_file = installer
        name = Path(installer).name
        self._reminder = ctk.CTkLabel(
            self,
            text=f"One last thing: the Essential installer ({name}) is still in your "
            "Downloads folder. It's done its job — you can delete it.",
            text_color=WARN, wraplength=520, justify="center",
        )
        self._reminder.pack(pady=(2, 6))
        self._del_btn = ctk.CTkButton(
            self, text="🗑  Delete it now", width=200, height=36, fg_color="gray30",
            hover_color="gray25", command=self._delete_installer,
        )
        self._del_btn.pack(pady=(0, 10))

    def _delete_installer(self) -> None:
        path = self._installer_file
        self._del_btn.configure(state="disabled", text="Deleting…")

        def work() -> None:
            essential.delete_installer(path, attempts=5, delay=0.5)
            self._safe(lambda: self._after_delete(path))

        self.wiz.run_async(work)

    def _after_delete(self, path: str) -> None:
        if not Path(path).exists():
            self._del_btn.configure(text="Deleted ✓")
            self._reminder.configure(
                text="Removed the Essential installer from your Downloads.",
                text_color=GOOD,
            )
        else:
            self._del_btn.configure(state="normal", text="🗑  Delete it now")
            self._reminder.configure(
                text="Couldn't delete it — it may still be open. Close the Essential "
                f"installer, or delete {Path(path).name} from Downloads yourself.",
                text_color=BAD,
            )

    def _again(self) -> None:
        # Keep the loaded manifest; clear the per-run choices.
        for key in ("mode", "version", "mods_dir", "install_name",
                    "installed_count", "installer_file"):
            self.wiz.ctx[key] = None
        self.wiz.show_page(WelcomePage)
