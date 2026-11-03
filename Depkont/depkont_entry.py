"""Windowed entry point used by PyInstaller. Running this file opens the panel."""

from __future__ import annotations

import os
import sys
import threading
import traceback
from pathlib import Path

# These imports are module-level so the frozen build collects Tk, Excel, and SAP COM.
import openpyxl  # noqa: F401
import pythoncom  # noqa: F401
import pywintypes  # noqa: F401
import tkinter  # noqa: F401
import win32api  # noqa: F401
import win32com.client  # noqa: F401
import win32con  # noqa: F401
import win32gui  # noqa: F401
import win32process  # noqa: F401


def _install_crash_log() -> None:
    if not getattr(sys, "frozen", False):
        return
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    def _write(exc_type, exc, tb) -> Path:
        path = Path(sys.executable).with_name("depkont-hata.log")
        path.write_text("".join(traceback.format_exception(exc_type, exc, tb)), encoding="utf-8")
        return path

    def _hook(exc_type, exc, tb) -> None:
        path = _write(exc_type, exc, tb)
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Depkont", f"Program açılamadı.\n{path}")
            root.destroy()
        except Exception:
            pass

    def _thread_hook(args) -> None:
        _write(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _hook
    threading.excepthook = _thread_hook


if __name__ == "__main__":
    _install_crash_log()
    from depkont.cli import main

    raise SystemExit(main())
