from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

# Running this file directly puts its folder on sys.path, not the project root.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from depkont import __version__
from depkont.sap_logon import SapLogonError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="depkont",
        description="Depo kontrol uygulaması",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"depkont {__version__}",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Paneli ve SAP oturumunu açmadan çalışma ortamını denetler.",
    )
    return parser


def _check_runtime() -> int:
    import tkinter  # noqa: F401
    import pythoncom  # noqa: F401
    import pywintypes  # noqa: F401
    import win32api  # noqa: F401
    import win32con  # noqa: F401
    import win32gui  # noqa: F401
    import win32process  # noqa: F401
    import win32com.client  # noqa: F401
    import openpyxl  # noqa: F401

    return 0


def main(
    argv: list[str] | None = None,
    runner: Callable[[], str] | None = None,
) -> int:
    args = build_parser().parse_args(argv)
    if args.check:
        return _check_runtime()
    if runner is None:
        from depkont.panel import run_panel

        run_panel()
        return 0
    try:
        message = runner()
    except SapLogonError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
