"""Download the pinned Tailwind CSS standalone CLI for this platform.

The binary is saved in the repository root as ``tailwindcss`` (``tailwindcss.exe`` on
Windows). Both names are gitignored. Re-running is a no-op when the recorded version matches.
"""

from __future__ import annotations

import platform
import stat
import sys
import urllib.request
from pathlib import Path

TAILWIND_VERSION = "v4.3.3"
ROOT = Path(__file__).resolve().parent.parent
VERSION_FILE = ROOT / "tailwindcss-version.txt"


def asset_name() -> str:
    system = platform.system()
    machine = platform.machine().lower()
    arm = machine in {"arm64", "aarch64"}
    if system == "Darwin":
        return "tailwindcss-macos-arm64" if arm else "tailwindcss-macos-x64"
    if system == "Windows":
        return "tailwindcss-windows-x64.exe"
    if system == "Linux":
        return "tailwindcss-linux-arm64" if arm else "tailwindcss-linux-x64"
    raise SystemExit(f"Unsupported platform: {system} {machine}")


def binary_path() -> Path:
    return ROOT / ("tailwindcss.exe" if platform.system() == "Windows" else "tailwindcss")


def main() -> int:
    target = binary_path()
    if (
        target.exists()
        and VERSION_FILE.exists()
        and VERSION_FILE.read_text().strip() == TAILWIND_VERSION
    ):
        print(f"Tailwind {TAILWIND_VERSION} already present at {target.name}")
        return 0

    url = (
        "https://github.com/tailwindlabs/tailwindcss/releases/download/"
        f"{TAILWIND_VERSION}/{asset_name()}"
    )
    print(f"Downloading {url}")
    tmp = target.with_suffix(target.suffix + ".part")
    with urllib.request.urlopen(url) as response, tmp.open("wb") as out:
        out.write(response.read())
    tmp.replace(target)
    if platform.system() != "Windows":
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    VERSION_FILE.write_text(TAILWIND_VERSION + "\n")
    print(f"Saved Tailwind {TAILWIND_VERSION} to {target.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
