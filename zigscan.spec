# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the macOS app.

Build with ./build-macos.sh, not by calling pyinstaller directly — the script
checks the things that silently produce a broken .app.

Two decisions worth knowing:

ONEDIR, not onefile. A onefile build unpacks itself to a temp directory on every
launch, which costs seconds each time and, worse, changes the path of the
bundled toolchain between runs. onedir keeps the layout stable and makes the
bundle inspectable when something misbehaves in the field.

pycatsniffer ships as DATA, not as frozen code. capture.py puts it on sys.path
and imports `Modules.*` at run time, so freezing it would leave those imports
looking for files that are not there. Its own dependencies — typer, rich, click,
pyserial — do have to be frozen, and PyInstaller cannot see them from a dynamic
import, so they are declared by hand below.
"""

from PyInstaller.utils.hooks import collect_all

datas = [
    ("tools/page.html", "tools"),
    ("tools/catsniffer-tools/pycatsniffer_bv3", "tools/catsniffer-tools/pycatsniffer_bv3"),
    ("samples", "samples"),
    ("docs", "docs"),
    ("LICENSE", "."),
    ("CREDITS.md", "."),
]

# The tool's own modules are imported by name after sys.path is extended, which
# PyInstaller's static analysis cannot follow.
hiddenimports = [
    "paths", "console", "capture", "census", "verdict", "wifi", "probe",
    "identify", "pcap_summary", "pcap_convert",
    # Pulled in by pycatsniffer at run time.
    "serial", "serial.tools", "serial.tools.list_ports",
    "typer", "click", "rich",
]

for package in ("typer", "rich", "click"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    datas += pkg_datas
    hiddenimports += pkg_hidden

a = Analysis(
    ["zigscan_app.py"],
    pathex=["tools"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PyInstaller"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="zigscan",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="zigscan",
)

app = BUNDLE(
    coll,
    name="zigscan.app",
    icon="assets/zigscan.icns",
    bundle_identifier="ai.auroraproject.zigscan",
    info_plist={
        "CFBundleName": "zigscan",
        "CFBundleDisplayName": "zigscan",
        "CFBundleShortVersionString": "0.3.0",
        "CFBundleVersion": "0.3.0",
        "NSHighResolutionCapable": True,
        # No window of its own: the console opens in the technician's default
        # browser, so the app has no dock UI to speak of. LSUIElement would hide
        # it entirely, but then there is no way to quit it — left visible on
        # purpose.
        "LSMinimumSystemVersion": "11.0",
        "NSHumanReadableCopyright": "GPL-3.0 · auroraproject.ai",
    },
)
