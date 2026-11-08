"""Compile Tailwind CSS: src/floorpro/static/css/input.css -> app.css.

Usage:
    uv run python scripts/build_css.py           # one-off minified build
    uv run python scripts/build_css.py --watch   # rebuild on template changes
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetch_tailwind import binary_path  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
CSS_DIR = ROOT / "src" / "floorpro" / "static" / "css"


def main(argv: list[str]) -> int:
    binary = binary_path()
    if not binary.exists():
        print(
            f"Tailwind CLI not found at {binary.name}. "
            "Run: uv run python scripts/fetch_tailwind.py",
            file=sys.stderr,
        )
        return 1
    cmd = [
        str(binary),
        "-i",
        str(CSS_DIR / "input.css"),
        "-o",
        str(CSS_DIR / "app.css"),
    ]
    cmd.append("--watch" if "--watch" in argv else "--minify")
    return subprocess.call(cmd, cwd=ROOT)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
