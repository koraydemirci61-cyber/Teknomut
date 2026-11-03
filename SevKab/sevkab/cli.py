from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Running this file directly puts its folder on sys.path, not the project root.
if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sevkab import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sevkab", description="SevKab uygulaması")
    parser.add_argument(
        "--version",
        action="version",
        version=f"sevkab {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print("SevKab hazır.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
