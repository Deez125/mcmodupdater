"""Wizard pages: Welcome -> Version -> [Essential] -> Sync -> Done.

Each page is a CTkFrame. The shared WizardApp (self.wiz) carries state between
them and runs slow work off-thread. Pages keep UI updates on the main thread via
self._safe(...).
"""

from __future__ import annotations

import io
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import BooleanVar, filedialog

import customtkinter as ctk
import requests
from PIL import Image, ImageDraw, ImageOps

from .. import (
    config,
    essential,
    manifest,
    minecraft,
    modsource,
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
        self.wiz.ctx["selected_optional"] = None
        if self.wiz.ctx["mode"] == "full":
            self.wiz.show_page(EssentialPage)
        else:
            self.wiz.show_page(ModSelectPage)


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
        self.wiz.show_page(ModSelectPage)


# --------------------------------------------------------------------------- #
# 4. Choose mods (the optional-mod picker)
# --------------------------------------------------------------------------- #
class ModSelectPage(Page):
    THUMB = (104, 58)  # preview thumbnail (px)
    RADIUS = 8
    INACTIVE = ("#C62828", "#FF6B6B")  # standout colour for the INACTIVE badge

    def on_show(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=6)
        self._img_refs: list = []     # keep CTkImage refs alive (Tk GC)
        self._checks: list = []       # (BooleanVar, resolved_mod) — every optional row
        self._sections: list = []     # per-category state dicts
        title_block(
            self, "Choose your mods",
            "Required mods install automatically. Tick any optional extras you want.",
        )
        self.status = ctk.CTkLabel(self, text="Loading the mod list…", text_color=MUTED)
        self.status.pack(pady=(0, 4))
        self.bar = ctk.CTkProgressBar(self, width=320, mode="indeterminate")
        self.bar.pack(pady=(0, 6))
        self.bar.start()
        self.wiz.run_async(
            self._load, on_error=lambda e: self._safe(lambda: self._load_failed(e))
        )

    def on_hide(self) -> None:
        try:
            self._pool.shutdown(wait=False, cancel_futures=True)
        except Exception:
            pass

    # -- load --
    def _load(self) -> None:
        data = self.wiz.ctx["manifest"]
        version = self.wiz.ctx["version"]
        ver = data["versions"][version]
        self._src = modsource.ModSource(data["source"])
        optional = [m for c in ver["optional"] for m in c["mods"]]
        resolved = self._src.resolve_optional(version, optional)  # network
        rmap = {r["name"]: r for r in resolved}
        self._safe(lambda: self._build(ver, rmap))

    def _load_failed(self, e: Exception) -> None:
        self.bar.stop()
        self.bar.pack_forget()
        self.status.configure(text=f"Couldn't load the mod list: {e}", text_color=BAD)
        ctk.CTkButton(self, text="← Back", fg_color="gray30", hover_color="gray25",
                      command=self._go_back).pack(pady=8)

    # -- build the list --
    def _build(self, ver: dict, rmap: dict) -> None:
        self.bar.stop()
        self.bar.pack_forget()
        self.status.pack_forget()

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        # Required: one locked, checked, non-expandable row.
        reqn = len(ver.get("required", []))
        reqrow = ctk.CTkFrame(scroll, fg_color=("gray82", "gray20"), corner_radius=6)
        reqrow.pack(fill="x", pady=(2, 8))
        self._req_var = BooleanVar(value=True)
        ctk.CTkCheckBox(
            reqrow, text=f"Required mods ({reqn})", variable=self._req_var,
            state="disabled", font=ctk.CTkFont(size=15, weight="bold"),
        ).pack(side="left", padx=10, pady=8)

        # Optional categories — each collapsible with a section select-all checkbox.
        for c in ver["optional"]:
            self._add_category(scroll, c, rmap)

        # Footer: select-all / clear / count + continue / back.
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(footer, text="Select all", width=84, height=28, fg_color="gray30",
                      hover_color="gray25", command=lambda: self._set_all(True)
                      ).pack(side="left")
        ctk.CTkButton(footer, text="Clear", width=64, height=28, fg_color="gray30",
                      hover_color="gray25", command=lambda: self._set_all(False)
                      ).pack(side="left", padx=6)
        self._count = ctk.CTkLabel(footer, text="", text_color=MUTED)
        self._count.pack(side="left", padx=8)
        ctk.CTkButton(footer, text="Continue →", height=40, width=150,
                      font=ctk.CTkFont(size=14, weight="bold"), command=self._continue
                      ).pack(side="right")
        ctk.CTkButton(footer, text="← Back", height=40, width=88, fg_color="gray30",
                      hover_color="gray25", command=self._go_back
                      ).pack(side="right", padx=(0, 8))
        self._update_count()

    def _add_category(self, parent, c: dict, rmap: dict) -> None:
        block = ctk.CTkFrame(parent, fg_color="transparent")
        block.pack(fill="x", pady=(8, 0))

        header = ctk.CTkFrame(block, fg_color=("gray84", "gray23"), corner_radius=6)
        header.pack(fill="x")
        state = {"var": BooleanVar(value=False), "content": None, "arrow": None,
                 "rows": [], "expanded": True}
        ctk.CTkCheckBox(
            header, text=c["category"], variable=state["var"],
            font=ctk.CTkFont(size=15, weight="bold"),
            command=lambda st=state: self._toggle_section(st),
        ).pack(side="left", padx=10, pady=6)
        state["arrow"] = ctk.CTkButton(
            header, text="▾", width=34, fg_color="transparent",
            hover_color=("gray74", "gray30"),
            command=lambda st=state: self._collapse(st),
        )
        state["arrow"].pack(side="right", padx=4)

        state["content"] = ctk.CTkFrame(block, fg_color="transparent")
        state["content"].pack(fill="x")
        for m in c["mods"]:
            self._add_row(state["content"], rmap[m["name"]], state)
        self._sections.append(state)

    def _add_row(self, parent, r: dict, state: dict) -> None:
        available = r.get("available", True)
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=3, padx=(14, 0))
        row.grid_columnconfigure(2, weight=1)

        var = BooleanVar(value=False)
        self._checks.append((var, r))
        state["rows"].append((var, r))
        cb = ctk.CTkCheckBox(row, text="", width=24, variable=var,
                             command=lambda st=state: self._on_mod_toggle(st))
        cb.grid(row=0, column=0, rowspan=2, padx=(2, 8), sticky="n")
        if not available:
            cb.configure(state="disabled")

        thumb = ctk.CTkLabel(row, text="", width=self.THUMB[0], height=self.THUMB[1],
                             fg_color="gray20", corner_radius=self.RADIUS)
        thumb.grid(row=0, column=1, rowspan=2, padx=(0, 10))
        self._pool.submit(self._load_image, r["image_url"], thumb, not available)

        namerow = ctk.CTkFrame(row, fg_color="transparent")
        namerow.grid(row=0, column=2, sticky="w")
        name_kw = {} if available else {"text_color": MUTED}
        ctk.CTkLabel(namerow, text=r["name"], anchor="w",
                     font=ctk.CTkFont(size=14, weight="bold"), **name_kw).pack(side="left")
        if not available:
            ctk.CTkLabel(namerow, text="  INACTIVE", text_color=self.INACTIVE,
                         font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkLabel(row, text=r["description"], anchor="w", text_color=MUTED,
                     wraplength=380, justify="left"
                     ).grid(row=1, column=2, sticky="w")

    def _load_image(self, url: str, label, dim: bool = False) -> None:
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            pil = Image.open(io.BytesIO(resp.content)).convert("RGBA")
            img = ImageOps.fit(pil, self.THUMB)          # cover + centre-crop to fill
            if dim:
                img = ImageOps.grayscale(img).convert("RGBA")
            mask = Image.new("L", self.THUMB, 0)
            ImageDraw.Draw(mask).rounded_rectangle(
                [0, 0, self.THUMB[0] - 1, self.THUMB[1] - 1], radius=self.RADIUS, fill=255)
            img.putalpha(mask)                            # rounded corners, no image edits
            cimg = ctk.CTkImage(light_image=img, dark_image=img, size=self.THUMB)
        except Exception:
            return  # leave the placeholder; image is cosmetic

        def apply() -> None:
            if label.winfo_exists():
                self._img_refs.append(cimg)
                label.configure(image=cimg, text="", fg_color="transparent")
        self._safe(apply)

    # -- interactions --
    def _collapse(self, state: dict) -> None:
        state["expanded"] = not state["expanded"]
        if state["expanded"]:
            state["content"].pack(fill="x")
            state["arrow"].configure(text="▾")
        else:
            state["content"].pack_forget()
            state["arrow"].configure(text="▸")

    def _toggle_section(self, state: dict) -> None:
        val = state["var"].get()
        for var, r in state["rows"]:
            if r.get("available", True):
                var.set(val)
        self._update_count()

    def _on_mod_toggle(self, state: dict) -> None:
        avail = [(v, r) for v, r in state["rows"] if r.get("available", True)]
        state["var"].set(bool(avail) and all(v.get() for v, _ in avail))
        self._update_count()

    def _set_all(self, value: bool) -> None:
        for var, r in self._checks:
            if r.get("available", True):
                var.set(value)
        for st in self._sections:
            has_avail = any(r.get("available", True) for _, r in st["rows"])
            st["var"].set(value if has_avail else False)
        self._update_count()

    def _update_count(self) -> None:
        n = sum(1 for var, _ in self._checks if var.get())
        self._count.configure(text=f"{n} selected")

    def _continue(self) -> None:
        self.wiz.ctx["selected_optional"] = [
            {"filename": r["filename"], "download_url": r["download_url"]}
            for var, r in self._checks
            if var.get() and r.get("available", True)
        ]
        self.wiz.show_page(SyncPage)

    def _go_back(self) -> None:
        target = EssentialPage if self.wiz.ctx["mode"] == "full" else VersionPage
        self.wiz.show_page(target)


# --------------------------------------------------------------------------- #
# 5. Download + install mods
# --------------------------------------------------------------------------- #
class SyncPage(Page):
    def on_show(self) -> None:
        title_block(self, "Installing mods")

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

        selected = self.wiz.ctx.get("selected_optional", [])

        def work() -> None:
            data = self.wiz.ctx["manifest"]
            src = modsource.ModSource(data["source"])
            self._log("Reading the mod list from GitHub…")
            required = dict(src.required_jars(version))
            jar_sources = dict(required)
            for sel in selected:
                jar_sources[sel["filename"]] = sel["download_url"]
            self._log(
                f"Installing {len(jar_sources)} mod(s) — "
                f"{len(required)} required + {len(selected)} optional…"
            )
            self._safe(lambda: (self.bar.stop(), self.bar.configure(mode="determinate"),
                                self.bar.set(0)))
            result = sync.install_jars(
                mods_dir, jar_sources, version, log=self._log,
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
                    "installed_count", "installer_file", "selected_optional"):
            self.wiz.ctx[key] = None
        self.wiz.show_page(WelcomePage)
