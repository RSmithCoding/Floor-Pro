"""Desktop launcher: local server on 127.0.0.1 shown in a native pywebview window.

This is the only module that imports ``webview``, so tests and CI never need a GUI.
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from floorpro.app import create_app

HOST = "127.0.0.1"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((HOST, 0))
        return sock.getsockname()[1]


def wait_until_up(url: str, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/healthz", timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("FloorPro's local server did not start in time")


def _documents_dir() -> Path:
    documents = Path.home() / "Documents"
    return documents if documents.is_dir() else Path.home()


def _first_path(result) -> Path | None:
    """pywebview returns a str, a tuple/list of str, or None when cancelled."""
    if not result:
        return None
    return Path(result if isinstance(result, str) else result[0])


class NativeDialogs:
    """Native Save, folder and Open dialogs for the desktop window (``app.state.dialogs``).

    The embedded web view opens files it can display instead of downloading them, and the
    window has no Back button, so FloorPro uses native dialogs rather than navigating to files.
    pywebview marshals each dialog onto the GUI thread, so these are safe to call from a request.
    Every method returns the chosen path, or ``None`` if the user cancelled.
    """

    BACKUP_FILE_TYPES = ("FloorPro backups (*.fpbackup)", "All files (*.*)")

    def __init__(self, webview, window):
        self._webview = webview
        self._window = window

    def save_path(self, filename: str) -> Path | None:
        result = self._window.create_file_dialog(
            self._webview.FileDialog.SAVE,
            directory=str(_documents_dir()),
            save_filename=filename,
        )
        return _first_path(result)

    def choose_folder(self) -> Path | None:
        result = self._window.create_file_dialog(
            self._webview.FileDialog.FOLDER, directory=str(_documents_dir())
        )
        return _first_path(result)

    def open_file(self) -> Path | None:
        result = self._window.create_file_dialog(
            self._webview.FileDialog.OPEN,
            directory=str(_documents_dir()),
            allow_multiple=False,
            file_types=self.BACKUP_FILE_TYPES,
        )
        return _first_path(result)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="floorpro", description="Run FloorPro")
    parser.add_argument(
        "--browser", action="store_true", help="open in your normal browser (development)"
    )
    args = parser.parse_args(argv)

    port = free_port()
    url = f"http://{HOST}:{port}"
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_config=None))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    wait_until_up(url)

    try:
        if args.browser:
            webbrowser.open(url)
            print(f"FloorPro is running at {url} (press Ctrl+C to stop)")
            while thread.is_alive():
                thread.join(0.5)
        else:
            import webview

            window = webview.create_window(
                "FloorPro", url, width=1280, height=820, min_size=(1024, 700)
            )
            app.state.dialogs = NativeDialogs(webview, window)
            webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
