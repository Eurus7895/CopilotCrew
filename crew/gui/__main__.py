"""Desktop-bundle entry point: ``python -m crew.gui``.

This is the script PyInstaller freezes into ``Crew.app`` / ``Crew.exe`` /
``Crew.AppImage``. It takes no arguments and boots straight into the
native window with default settings — end users double-click the app
icon, the window appears, no terminal involvement.

Developers can still invoke the CLI (``crew gui`` with all its flags)
for day-to-day work; this module exists so the bundled binary has a
simple, argparse-free entrypoint that PyInstaller can freeze cleanly.
"""

from __future__ import annotations


def main() -> None:
    from crew.gui.server import run_server
    run_server(open_window=True)


if __name__ == "__main__":
    main()
