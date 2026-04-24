"""Convenience wrapper around PyInstaller for building Crew desktop bundles.

Run from the repo root:

    python packaging/build.py            # clean build
    python packaging/build.py --keep     # incremental (skip cleaning dist/)

Outputs:
    dist/Crew/            onedir bundle (cross-platform)
    dist/Crew.app/        macOS application bundle
    dist/Crew.exe         Windows launcher (inside dist/Crew/)

Prereqs:
    pip install -e '.[gui,package]'
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SPEC = REPO_ROOT / "packaging" / "crew_gui.spec"
DIST = REPO_ROOT / "dist"
BUILD = REPO_ROOT / "build"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Crew desktop bundle.")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Keep dist/ and build/ between runs (incremental build).",
    )
    parser.add_argument(
        "--log-level",
        default="WARN",
        choices=["TRACE", "DEBUG", "INFO", "WARN", "ERROR"],
        help="PyInstaller log level.",
    )
    args = parser.parse_args()

    if not args.keep:
        for d in (DIST, BUILD):
            if d.exists():
                shutil.rmtree(d)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        sys.stderr.write(
            "PyInstaller is not installed.\n"
            "Install the packaging extra:\n"
            "    pip install -e '.[gui,package]'\n"
        )
        return 2

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--log-level", args.log_level,
        str(SPEC),
    ]
    print(">>", " ".join(cmd))
    result = subprocess.run(cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        return result.returncode

    print()
    print("Built:")
    for path in sorted(DIST.iterdir()) if DIST.exists() else []:
        print(f"  {path.relative_to(REPO_ROOT)}")
    if sys.platform == "darwin":
        app = DIST / "Crew.app"
        if app.exists():
            print()
            print(f"Launch with:  open {app.relative_to(REPO_ROOT)}")
    elif sys.platform == "win32":
        exe = DIST / "Crew" / "Crew.exe"
        if exe.exists():
            print()
            print(f"Launch with:  {exe.relative_to(REPO_ROOT)}")
    else:
        exe = DIST / "Crew" / "Crew"
        if exe.exists():
            print()
            print(f"Launch with:  ./{exe.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
