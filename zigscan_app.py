#!/usr/bin/env python3
"""Entry point for the packaged app.

Two jobs in one binary, chosen by argv:

  (no arguments)     start the console and open the technician's browser
  --capture-worker   run one capture and exit

The second exists because the console runs captures in a separate process, so a
hung radio cannot take the whole app with it. Frozen, `sys.executable` is this
binary and there is no .py file to hand it — so it re-invokes itself with a flag
instead. See paths.worker_argv().
"""

from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))

import paths  # noqa: E402


def run_worker() -> int:
    import capture  # noqa: PLC0415
    sys.argv = [sys.argv[0], *sys.argv[2:]]
    return capture.main()


def run_console() -> int:
    import console  # noqa: PLC0415

    paths.ensure_data()

    port = int(os.environ.get("ZIGSCAN_PORT", "8477"))
    url = f"http://127.0.0.1:{port}/"

    # Open the browser from a thread, after the server is actually accepting
    # connections. Opening it first shows the technician a connection error and
    # teaches them the tool is broken.
    def open_when_up() -> None:
        import socket  # noqa: PLC0415
        for _ in range(60):
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    webbrowser.open(url)
                    return
            time.sleep(0.25)

    threading.Thread(target=open_when_up, daemon=True).start()

    print(f"zigscan — {url}")
    print(f"capturas en {paths.CAPTURES}")
    sys.argv = [sys.argv[0], "--port", str(port)]
    return console.main()


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--capture-worker":
        return run_worker()
    return run_console()


if __name__ == "__main__":
    sys.exit(main())
