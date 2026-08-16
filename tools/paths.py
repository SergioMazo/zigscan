#!/usr/bin/env python3
"""Where things live, in a checkout and inside a packaged app.

These are two different questions and the code used to conflate them, because in
a git checkout the answer is the same folder for both:

  RESOURCES  the page, the Electronic Cats toolchain, firmware images. Read-only
             and shipped with the program. Inside a .app they sit in the bundle,
             which macOS mounts read-only — writing there fails, and on a signed
             app it breaks the signature.

  DATA       captures, sweep manifests. Written at run time and owned by the
             technician, not by the program. They must outlive an uninstall and
             survive the app being replaced by a new version.

Captures go to ~/Documents/zigscan on purpose rather than Application Support:
a technician has to attach a pcap to a job file, and a folder they cannot find
in Finder is a folder they will not use.
"""

from __future__ import annotations

import pathlib
import sys

FROZEN = bool(getattr(sys, "frozen", False))

if FROZEN:
    # PyInstaller unpacks bundled data here.
    RESOURCES = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(sys.executable).parent))
    DATA = pathlib.Path.home() / "Documents" / "zigscan"
else:
    RESOURCES = pathlib.Path(__file__).resolve().parent.parent
    DATA = RESOURCES

CAPTURES = DATA / "captures"
PYCATSNIFFER = RESOURCES / "tools" / "catsniffer-tools" / "pycatsniffer_bv3"
PAGE = RESOURCES / "tools" / "page.html"
FIRMWARE = RESOURCES / "firmware"
SAMPLES = RESOURCES / "samples"


def ensure_data() -> pathlib.Path:
    """Create the writable tree and seed it the first time it is used."""
    CAPTURES.mkdir(parents=True, exist_ok=True)
    # Seed the samples so a fresh install renders a real chart instead of an
    # empty one. Copied, never linked: the technician may delete them.
    if FROZEN and SAMPLES.is_dir():
        for sample in SAMPLES.glob("*.pcap"):
            target = CAPTURES / sample.name
            if not target.exists():
                target.write_bytes(sample.read_bytes())
    return DATA


def worker_argv(*args: str) -> list[str]:
    """How to re-invoke ourselves to run a capture.

    Frozen, sys.executable is the app binary and there is no .py to hand it, so
    the entry point dispatches on a flag instead. From a checkout it is a normal
    interpreter and the script path works.
    """
    if FROZEN:
        return [sys.executable, "--capture-worker", *args]
    return [sys.executable, str(RESOURCES / "tools" / "capture.py"), *args]
