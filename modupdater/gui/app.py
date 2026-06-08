"""The wizard shell.

A WizardApp holds shared state and swaps full-screen "pages" in and out. Each
page is a small self-contained step (Welcome -> Version -> [Essential] -> Sync ->
Done), so the flow stays dead simple for non-technical users. All slow work runs
on a worker thread via `run_async`; pages talk back to the UI through `after`.
"""

from __future__ import annotations

import threading
import traceback
from typing import Callable, Type

import customtkinter as ctk

from .. import config

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class WizardApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{config.SERVER_NAME} · {config.APP_NAME}")
        self.geometry("660x620")
        self.minsize(600, 560)
        self._apply_window_icon()

        # Shared state carried across pages. (Named `ctx`, not `state`, because
        # Tkinter's CTk already has a `state()` method we must not shadow.)
        self.ctx: dict = {
            "manifest": None,     # parsed manifest dict
            "mode": None,         # "full" | "update"
            "version": None,      # chosen version string
            "mods_dir": None,     # resolved Path to the mods folder
            "install_name": None, # Essential install folder name, for the Done screen
        }

        self.container = ctk.CTkFrame(self, fg_color="transparent")
        self.container.pack(fill="both", expand=True)
        self.current = None

        # Imported here to avoid a circular import at module load.
        from . import pages
        self.pages = pages
        self.show_page(pages.WelcomePage)

    def _apply_window_icon(self) -> None:
        """Use icon.png for the window/taskbar icon. Cosmetic; ignore failures."""
        path = config.icon_path()
        if path is None:
            return
        try:
            from PIL import Image, ImageTk

            self._win_icon = ImageTk.PhotoImage(Image.open(path))
            self.iconphoto(True, self._win_icon)
        except Exception:
            pass

    def show_page(self, page_cls: Type) -> None:
        if self.current is not None:
            try:
                self.current.on_hide()
            except Exception:
                pass
            self.current.destroy()
        self.current = page_cls(self)
        self.current.pack(fill="both", expand=True)
        self.current.on_show()

    def run_async(
        self, fn: Callable[[], None], on_error: Callable[[Exception], None] | None = None
    ) -> None:
        """Run `fn` off the UI thread. Exceptions go to `on_error` (or are logged)."""

        def runner() -> None:
            try:
                fn()
            except Exception as e:
                err = e  # `e` is cleared when the except block exits; keep a ref
                if on_error is not None:
                    self.after(0, lambda err=err: on_error(err))
                else:
                    traceback.print_exc()

        threading.Thread(target=runner, daemon=True).start()


def main() -> None:
    WizardApp().mainloop()


if __name__ == "__main__":
    main()
