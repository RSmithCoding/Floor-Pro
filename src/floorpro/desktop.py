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


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="floorpro", description="Run FloorPro")
    parser.add_argument(
        "--browser", action="store_true", help="open in your normal browser (development)"
    )
    args = parser.parse_args(argv)

    port = free_port()
    url = f"http://{HOST}:{port}"
    server = uvicorn.Server(uvicorn.Config(create_app(), host=HOST, port=port, log_config=None))
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

            webview.settings["ALLOW_DOWNLOADS"] = True
            webview.create_window("FloorPro", url, width=1280, height=820, min_size=(1024, 700))
            webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
