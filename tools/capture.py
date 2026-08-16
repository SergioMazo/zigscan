#!/usr/bin/env python3
"""Capture, in this process. No bash, no second virtualenv, no subprocess.

This replaces scan_channels.sh and sniff_zigbee.sh, which drove pycatsniffer by
launching `.venv/bin/python cat_sniffer.py` and piping commands into its REPL.
That worked on a developer's bench and cannot survive being packaged: inside a
.app there is no .venv, no absolute paths and no second interpreter to launch.

Driving Electronic Cats' SnifferCollector directly is the same work with none of
that. It also removes the last reason the project needed two virtualenvs, and it
is the change that makes a Windows build possible later.

Run:  ./zigscan scan [seconds]
      ./zigscan capture <channel> <seconds> [name]
"""

from __future__ import annotations

import glob
import json
import logging
import os
import pathlib
import struct
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths  # noqa: E402

PYCAT = paths.PYCATSNIFFER

RPI_HEADER_LEN = 20

LANG = os.environ.get("ZIGSCAN_LANG", "es").lower()

MESSAGES = {
    "es": {
        "missing_toolchain": "No se encontró pycatsniffer en {path}. Ejecutá ./setup.sh primero.",
        "no_radio": "No se encontró un CatSniffer (se buscó /dev/cu.usbmodem*).",
        "open_failed": "No se pudo abrir {port}. ¿Hay otra captura en curso?",
        "sweep_start": "Barrido de canales Zigbee — {dwell}s por canal, {count} canales",
        "captures_arrow": "capturas -> {path}",
        "activity": "*** ACTIVIDAD ***",
        "recommended_clear": "RECOMENDADO: canal {channel} ({mhz} MHz) — sin tráfico Zigbee y fuera de Wi-Fi 1/6/11.",
        "recommended_best": "RECOMENDADO: canal {channel} ({mhz} MHz) — el más limpio de los que esquivan Wi-Fi ({frames} tramas).",
        "busiest": "Canal más ocupado: {channel} ({frames} tramas en {dwell}s).",
        "captures_at": "Capturas en {path}",
        "no_traffic": "No se encontró tráfico Zigbee en ningún canal.",
        "before_clear": "Antes de concluir que el aire está limpio, descartá lo barato:",
        "antenna_1": "- ¿Tiene antena de 2.4 GHz enroscada en el SMA? Sin ella el",
        "antenna_2": "  espectro se ve vacío exactamente igual que uno limpio.",
        "quiet_1": "- Zigbee es muy callado en reposo. Pedí que prendan y apaguen",
        "quiet_2": "  una luz durante el barrido para forzar tráfico.",
        "dwell_more": "- {dwell}s por canal puede no alcanzar. Probá con 15.",
        "capture_start": "Capturando canal {channel} durante {seconds}s -> {path}",
        "captured": "{frames} tramas capturadas.",
        "no_frames": "Sin tramas. La red puede estar en reposo — ver docs/MANUAL.md §7.",
    },
    "en": {
        "missing_toolchain": "pycatsniffer was not found at {path}. Run ./setup.sh first.",
        "no_radio": "No CatSniffer found (looked for /dev/cu.usbmodem*).",
        "open_failed": "Could not open {port}. Is another capture running?",
        "sweep_start": "Zigbee channel sweep — {dwell}s per channel, {count} channels",
        "captures_arrow": "captures -> {path}",
        "activity": "*** ACTIVITY ***",
        "recommended_clear": "RECOMMENDED: channel {channel} ({mhz} MHz) — no Zigbee traffic and clear of Wi-Fi 1/6/11.",
        "recommended_best": "RECOMMENDED: channel {channel} ({mhz} MHz) — the clearest option outside Wi-Fi ({frames} frames).",
        "busiest": "Busiest channel: {channel} ({frames} frames in {dwell}s).",
        "captures_at": "Captures in {path}",
        "no_traffic": "No Zigbee traffic was found on any channel.",
        "before_clear": "Before concluding that the air is clear, rule out the simple causes:",
        "antenna_1": "- Is a 2.4 GHz antenna attached to the SMA port? Without it,",
        "antenna_2": "  the spectrum looks empty exactly like a genuinely clear site.",
        "quiet_1": "- Idle Zigbee is very quiet. Ask someone to toggle a light",
        "quiet_2": "  during the sweep to produce traffic.",
        "dwell_more": "- {dwell}s per channel may not be enough. Try 15.",
        "capture_start": "Capturing channel {channel} for {seconds}s -> {path}",
        "captured": "{frames} frames captured.",
        "no_frames": "No frames. The network may be idle — see docs/MANUAL.md §7.",
    },
}


def msg(key: str, lang: str | None = None, **values) -> str:
    """Return console prose in the UI-selected language."""
    selected = lang if lang in MESSAGES else LANG
    selected = selected if selected in MESSAGES else "es"
    return MESSAGES[selected][key].format(**values)


def _load_pycatsniffer():
    """Import Electronic Cats' modules from the vendored checkout.

    Their package uses relative imports, so the checkout root has to be on
    sys.path and the package imported by name — importing the files directly
    would break on the first `from .Utils import`.
    """
    if not PYCAT.is_dir():
        raise RuntimeError(msg("missing_toolchain", path=PYCAT))
    if str(PYCAT) not in sys.path:
        sys.path.insert(0, str(PYCAT))
    from Modules import PcapDumper  # noqa: PLC0415
    from Modules import SnifferCollector  # noqa: PLC0415

    if not VERBOSE:
        _silence(SnifferCollector)
    return SnifferCollector, PcapDumper


# Set ZIGSCAN_VERBOSE=1 to see pycatsniffer's own chatter while debugging.
VERBOSE = bool(os.environ.get("ZIGSCAN_VERBOSE"))


def _silence(SnifferCollector) -> None:
    """Stop pycatsniffer printing over our output.

    Its LOG_* helpers are bare `print()` calls with ANSI colour, and a malformed
    frame from a neighbour's network — which is normal on a busy channel —
    produces a multi-line dissector warning per packet. Those land in the
    console's job log and bury the channel results the technician is reading.

    They are patched on SnifferCollector rather than on Utils because it did
    `from .Utils import LOG_WARNING`, binding the names at import time; patching
    Utils afterwards would change nothing.
    """
    def quiet(*_args, **_kwargs) -> None:
        return None

    for name in ("LOG_INFO", "LOG_WARNING", "LOG_ERROR"):
        if hasattr(SnifferCollector, name):
            setattr(SnifferCollector, name, quiet)

    logging.getLogger("Modules.Logger").setLevel(logging.CRITICAL)
    logging.getLogger("Modules.SnifferCollector").setLevel(logging.CRITICAL)

    # stop_workers() signs off with typer.echo("Stoping workers"), which lands in
    # the middle of the channel table. Only echo is stubbed — the rest of typer
    # stays intact in case upstream reaches for it.
    typer_mod = getattr(SnifferCollector, "typer", None)
    if typer_mod is not None and hasattr(typer_mod, "echo"):
        class _QuietTyper:
            def __init__(self, real):
                self._real = real

            def __getattr__(self, name):
                return getattr(self._real, name)

            def echo(self, *_args, **_kwargs):
                return None

        SnifferCollector.typer = _QuietTyper(typer_mod)


def find_port() -> str | None:
    """The CatSniffer's CDC port.

    Only cu.usbmodem*: the RP2040 is a native-USB device and macOS names those
    usbmodem. cu.usbserial* is a USB-UART bridge — somebody else's radio — and
    opening one mid-capture would disturb a live network.
    """
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    return ports[0] if ports else None


def count_frames(path: pathlib.Path) -> int:
    """Records in a pcap, not counting the tool's own leading config frame."""
    try:
        data = path.read_bytes()
    except OSError:
        return 0
    if len(data) < 24:
        return 0
    magic, *_rest, link = struct.unpack("<LHHIILL", data[:24])
    if magic != 0xA1B2C3D4:
        return 0
    n, off = 0, 24
    while off + 16 <= len(data):
        _ts, _us, caplen, _orig = struct.unpack("<llll", data[off : off + 16])
        off += 16 + caplen
        if caplen < 0:
            break
        n += 1
    return n


def _pinned_dumper(PcapDumper, path: pathlib.Path):
    """A PcapDumper that writes where we say.

    Upstream's get_filename() calls generate_filename(), which mixes a timestamp
    with a fresh uuid4 on *every call* — and run() calls it three times, so even
    upstream cannot name the file it just opened. That is why the old shell
    scripts had to `find` the result afterwards. Pinning the path removes the
    guesswork instead of guessing better.
    """

    class PinnedPcapDumper(PcapDumper.PcapDumper):
        def __init__(self, target: pathlib.Path) -> None:
            super().__init__(str(target))
            self._target = str(target)

        def get_filename(self) -> str:
            return self._target

    path.parent.mkdir(parents=True, exist_ok=True)
    return PinnedPcapDumper(path)


def capture(channel: int, seconds: float, out_path: pathlib.Path,
            port: str | None = None, phy: str = "zigbee") -> int:
    """Listen on one channel and write a pcap. Returns frames captured.

    Receive only. The sniffer firmware cannot transmit, so this is safe to run
    inside a customer's live network.
    """
    SnifferCollector, PcapDumper = _load_pycatsniffer()

    port = port or find_port()
    if not port:
        raise RuntimeError(msg("no_radio"))

    collector = SnifferCollector.SnifferCollector()
    if not VERBOSE and hasattr(collector, "logger"):
        collector.logger = logging.getLogger("zigscan.silenced")
        collector.logger.addHandler(logging.NullHandler())
        collector.logger.propagate = False
    if not collector.set_board_uart(port):
        raise RuntimeError(msg("open_failed", port=port))

    # Order matters: set_protocol_phy computes the pcap linktype, and the
    # collector only hands it to the dumper when the workers start. Setting the
    # phy after run_workers() writes a header for the wrong link type.
    collector.set_protocol_phy(phy)
    collector.set_protocol_channel(channel)

    dumper = _pinned_dumper(PcapDumper, out_path)
    collector.set_output_workers([dumper])

    try:
        collector.run_workers()
        time.sleep(seconds)
    finally:
        collector.stop_workers()
        with_suppress = getattr(collector, "close_board_uart", None)
        if with_suppress:
            try:
                with_suppress()
            except Exception:  # noqa: BLE001  closing must never mask a result
                pass
        time.sleep(0.3)  # let the dumper thread flush its last write

    frames = count_frames(out_path)
    if frames == 0:
        out_path.unlink(missing_ok=True)
    return frames


# Zigbee 15, 20, 25 and 26 fall in the gaps between Wi-Fi 1, 6 and 11.
PREFERRED = (15, 20, 25, 26)
ALL_CHANNELS = tuple(range(11, 27))


def sweep(channels=ALL_CHANNELS, dwell: float = 6, outdir: pathlib.Path | None = None,
          port: str | None = None) -> dict:
    """Walk the channels and report what was heard on each.

    Writes a manifest of every channel visited, including the silent ones.
    Without it, a channel measured and found clear is indistinguishable from a
    channel nobody listened to — and the console would recommend a channel it
    has never heard.
    """
    stamp = time.strftime("%Y%m%d-%H%M%S")
    outdir = outdir or (paths.CAPTURES / f"scan-{stamp}")
    paths.ensure_data()
    outdir.mkdir(parents=True, exist_ok=True)

    port = port or find_port()
    if not port:
        raise RuntimeError(msg("no_radio"))

    print()
    print("  " + msg("sweep_start", dwell=f"{dwell:g}", count=len(channels)))
    print("  " + msg("captures_arrow", path=outdir))
    print()
    frame_label = "tramas" if LANG == "es" else "frames"
    note_label = "notas" if LANG == "es" else "notes"
    print(f"  {'ch':<4} {'MHz':<10} {frame_label:<8} {note_label}")
    print(f"  {'----':<4} {'----------':<10} {'--------':<8} -----")

    counts: dict[int, int] = {}
    for ch in channels:
        freq = 2405 + 5 * (ch - 11)
        dest = outdir / f"ch{ch}.pcap"
        try:
            n = capture(ch, dwell, dest, port=port)
        except RuntimeError as exc:
            print(f"  {ch:<4} {freq:<10} {'-':<8} {exc}")
            counts[ch] = 0
            continue
        counts[ch] = n
        # Keep this column layout: the console parses these lines to drive its
        # progress bar.
        print(f"  {ch:<4} {freq:<10} {n:<8} {msg('activity') if n else ''}", flush=True)

    manifest = paths.CAPTURES / f"scan-{stamp}.json"
    manifest.write_text(json.dumps({
        "dwell": dwell,
        "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "channels": {str(c): counts.get(c, 0) for c in channels},
    }) + "\n")

    try:
        outdir.rmdir()          # empty when nothing was heard
    except OSError:
        pass

    print()
    busy = {c: n for c, n in counts.items() if n}
    measured = [c for c in PREFERRED if c in counts]
    if measured:
        pick = min(measured, key=lambda c: (counts[c], c))
        freq = 2405 + 5 * (pick - 11)
        if counts[pick] == 0:
            print("  " + msg("recommended_clear", channel=pick, mhz=freq))
        else:
            print("  " + msg("recommended_best", channel=pick, mhz=freq,
                              frames=counts[pick]))
        print()

    if busy:
        loudest = max(busy, key=lambda c: busy[c])
        print("  " + msg("busiest", channel=loudest, frames=busy[loudest],
                         dwell=f"{dwell:g}"))
        print("  " + msg("captures_at", path=outdir))
    else:
        print("  " + msg("no_traffic"))
        print()
        print("  " + msg("before_clear"))
        print("    " + msg("antenna_1"))
        print("    " + msg("antenna_2"))
        print("    " + msg("quiet_1"))
        print("    " + msg("quiet_2"))
        print("    " + msg("dwell_more", dwell=f"{dwell:g}"))
    print()
    return counts


def main() -> int:
    # Line-buffer stdout. Frozen and windowed, this process has no tty, so
    # Python block-buffers by default and the console's progress bar sits at
    # zero for two minutes and then jumps to done. The bar is the whole reason
    # the technician does not press the button twice.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except (AttributeError, ValueError):
        pass

    args = sys.argv[1:]
    if args and args[0] == "capture":
        if len(args) < 3:
            print("usage: capture <channel> <seconds> [name]", file=sys.stderr)
            return 2
        ch, secs = int(args[1]), float(args[2])
        name = args[3] if len(args) > 3 else f"ch{ch}-{time.strftime('%Y%m%d-%H%M%S')}"
        paths.ensure_data()
        dest = paths.CAPTURES / f"{name}.pcap"
        print("\n  " + msg("capture_start", channel=ch, seconds=f"{secs:g}",
                             path=dest) + "\n")
        n = capture(ch, secs, dest)
        print("  " + (msg("captured", frames=n) if n else msg("no_frames")) + "\n")
        return 0

    dwell = float(args[0]) if args else 6
    chans = [int(a) for a in args[1:]] if len(args) > 1 else list(ALL_CHANNELS)
    sweep(chans, dwell)
    return 0


if __name__ == "__main__":
    sys.exit(main())
