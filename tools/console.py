#!/usr/bin/env python3
"""zigscan — Zigbee site survey console.

A small local web app — stdlib only. It does what a published web page cannot:
detect the radio's serial port, sweep the 16 Zigbee channels, and show which
ones are busy, which collide with Wi-Fi, and which are clear.

Runs on localhost only. Long jobs (scan, capture) run in background threads and
stream their output to the browser, so a two-minute sweep is watchable.

The radio is a passive receiver here. The CatSniffer runs TI sniffer firmware:
it listens on one channel at a time and transmits nothing, which is why a survey
is safe to run inside a live customer network — it cannot join, pair, or
disturb anything.

Run:  ./.venv/bin/python tools/console.py
      then open http://127.0.0.1:8477
"""

from __future__ import annotations

import argparse
import html
import http.server
import json
import os
import pathlib
import re
import shutil
import socketserver
import struct
import subprocess
import sys
import threading
import time
import uuid

LAB = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(LAB / "tools"))

import census  # noqa: E402
import paths  # noqa: E402
import probe as lab_report  # noqa: E402  hardware probes live in one place
import verdict  # noqa: E402
import wifi  # noqa: E402

RPI_HEADER_LEN = 20

FRAME_TYPES = {0: "Beacon", 1: "Data", 2: "ACK", 3: "MAC Command",
               4: "reserved", 5: "Multipurpose", 6: "Fragment", 7: "Extended"}
MAC_COMMANDS = {
    0x01: "Association Request", 0x02: "Association Response",
    0x03: "Disassociation", 0x04: "Data Request", 0x05: "PAN ID Conflict",
    0x06: "Orphan Notification", 0x07: "Beacon Request",
    0x08: "Coordinator Realignment", 0x09: "GTS Request",
}
# Control4's OUI. A source address starting with this proves Control4 hardware.
C4_OUI = "00:0f:ff"


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------
class Job:
    def __init__(self, kind: str, argv: list[str], cwd: pathlib.Path,
                 lang: str = "es") -> None:
        self.id = uuid.uuid4().hex[:8]
        self.kind = kind
        self.argv = argv
        self.cwd = cwd
        self.lines: list[str] = []
        self.status = "running"
        self.rc: int | None = None
        self.started = time.time()
        self.proc: subprocess.Popen | None = None
        self.lock = threading.Lock()
        self.env = os.environ.copy()
        self.env["ZIGSCAN_LANG"] = lang if lang in {"es", "en"} else "es"

    def run(self) -> None:
        try:
            self.proc = subprocess.Popen(
                self.argv, cwd=str(self.cwd), stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1, env=self.env,
            )
            assert self.proc.stdout is not None
            for raw in self.proc.stdout:
                line = raw.rstrip("\n")
                # pycatsniffer's REPL spams this once stdin closes; it is noise.
                if "Unknown syntax" in line:
                    continue
                line = re.sub(r"\x1b\[[0-9;]*m", "", line)
                if not line.strip():
                    continue
                with self.lock:
                    self.lines.append(line)
                    if len(self.lines) > 4000:
                        del self.lines[:1000]
            self.rc = self.proc.wait()
            self.status = "done" if self.rc == 0 else "failed"
        except Exception as exc:  # noqa: BLE001
            with self.lock:
                self.lines.append(f"[console] {type(exc).__name__}: {exc}")
            self.status = "failed"
            self.rc = -1

    def snapshot(self, since: int = 0) -> dict:
        with self.lock:
            return {
                "id": self.id, "kind": self.kind, "status": self.status,
                "rc": self.rc, "elapsed": round(time.time() - self.started, 1),
                "lines": self.lines[since:], "total": len(self.lines),
            }

    def cancel(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.status = "cancelled"


JOBS: dict[str, Job] = {}
JOBS_LOCK = threading.Lock()


def start_job(kind: str, argv: list[str], cwd: pathlib.Path = LAB,
              lang: str = "es") -> Job:
    job = Job(kind, argv, cwd, lang=lang)
    with JOBS_LOCK:
        # Only one hardware job at a time — they all contend for the serial port.
        for other in JOBS.values():
            if other.status == "running":
                raise RuntimeError(
                    f"a {other.kind} job is still running; wait for it or cancel it"
                )
        JOBS[job.id] = job
    threading.Thread(target=job.run, daemon=True).start()
    return job


# ---------------------------------------------------------------------------
# pcap decoding for the technician view
# ---------------------------------------------------------------------------
def _addr(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in reversed(b))


def decode_pcap(path: pathlib.Path, limit: int = 500) -> dict:
    """Decode a CatSniffer pcap into rows a technician can read."""
    data = path.read_bytes()
    if len(data) < 24:
        return {"rows": [], "note": "file too short", "note_code": "file_too_short"}
    magic, _vM, _vm, _tz, _sig, _snap, link = struct.unpack("<LHHIILL", data[:24])
    if magic != 0xA1B2C3D4:
        return {"rows": [], "note": "not a pcap", "note_code": "not_pcap"}

    rows: list[dict] = []
    off, t0 = 24, None
    while off + 16 <= len(data) and len(rows) < limit:
        ts, us, caplen, _ol = struct.unpack("<llll", data[off : off + 16])
        rec = data[off + 16 : off + 16 + caplen]
        off += 16 + caplen
        if caplen < 0:
            break

        ch = rssi = None
        if link == 147:
            if len(rec) < RPI_HEADER_LEN:
                continue
            ch = struct.unpack("<H", rec[12:14])[0]
            rssi = struct.unpack("<b", rec[14:15])[0]
            frame = rec[RPI_HEADER_LEN : RPI_HEADER_LEN + rec[19]]
        else:
            frame = rec
        if len(frame) < 3:
            continue

        if t0 is None:
            t0 = ts
        fcf = struct.unpack("<H", frame[:2])[0]
        ftype = fcf & 0x7
        dst_mode = (fcf >> 10) & 0x3
        src_mode = (fcf >> 14) & 0x3
        label = FRAME_TYPES.get(ftype, f"type{ftype}")
        detail, src, dst = "", "", ""

        i = 3
        try:
            if dst_mode:
                dst_pan = struct.unpack("<H", frame[i : i + 2])[0]
                i += 2
                if dst_mode == 2:
                    dst = f"0x{struct.unpack('<H', frame[i:i + 2])[0]:04x}"
                    i += 2
                elif dst_mode == 3:
                    dst = _addr(frame[i : i + 8])
                    i += 8
                dst = f"{dst} (PAN 0x{dst_pan:04x})"
            if src_mode:
                if not (fcf & 0x40):  # no PAN compression
                    i += 2
                if src_mode == 2:
                    src = f"0x{struct.unpack('<H', frame[i:i + 2])[0]:04x}"
                    i += 2
                elif src_mode == 3:
                    src = _addr(frame[i : i + 8])
                    i += 8
            if ftype == 3 and i < len(frame):
                detail = MAC_COMMANDS.get(frame[i], f"cmd 0x{frame[i]:02x}")
        except (struct.error, IndexError):
            detail = detail or "truncated"

        rows.append({
            "t": round((ts - t0) + us / 1e6, 3),
            "ch": ch, "rssi": rssi, "len": len(frame),
            "type": label, "detail": detail, "src": src, "dst": dst,
            "c4": bool(src and src.startswith(C4_OUI)),
            "secured": bool(fcf & 0x8),
            "hex": frame[:32].hex(" "),
        })
    return {"rows": rows, "linktype": link}


def capture_display_name(path: pathlib.Path) -> str:
    """Disambiguate per-scan channel files without changing their storage path."""
    parent = path.parent.name
    match = re.fullmatch(r"scan-\d{8}-(\d{6})", parent)
    if match:
        return f"scan-{match.group(1)} / {path.name}"
    if path.parent != paths.CAPTURES:
        return f"{parent} / {path.name}"
    return path.name


def list_captures() -> list[dict]:
    out = []
    for p in sorted(paths.CAPTURES.rglob("*.pcap"), key=lambda q: -q.stat().st_mtime):
        if p.name.endswith(".15p4.pcap"):
            continue
        dec = decode_pcap(p, limit=1)
        out.append({
            "path": str(p.relative_to(paths.DATA)),
            "name": p.name,
            "display_name": capture_display_name(p),
            "bytes": p.stat().st_size,
            "mtime": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
            "frames": len(decode_pcap(p, limit=10000)["rows"]),
            "linktype": dec.get("linktype"),
        })
    return out


def spectrum() -> dict:
    """Per-channel occupancy across all captures — feeds the 2.4 GHz graphic.

    Reuses the same RPI-header parse as the rest of the tool: channel and RSSI
    come straight off each record, so the graphic reflects what the radio
    actually heard, never a hand-kept number.
    """
    per: dict[int, dict] = {}
    for p in paths.CAPTURES.rglob("*.pcap"):
        if p.name.endswith(".15p4.pcap"):
            continue
        data = p.read_bytes()
        if len(data) < 24:
            continue
        magic, *_r, link = struct.unpack("<LHHIILL", data[:24])
        if magic != 0xA1B2C3D4 or link != 147:
            continue
        off = 24
        while off + 16 <= len(data):
            _t, _u, cl, _o = struct.unpack("<llll", data[off : off + 16])
            rec = data[off + 16 : off + 16 + cl]
            off += 16 + cl
            if cl < 0 or len(rec) < RPI_HEADER_LEN:
                continue
            ch = struct.unpack("<H", rec[12:14])[0]
            rssi = struct.unpack("<b", rec[14:15])[0]
            if rec[19] == 0:
                continue
            if not 11 <= ch <= 26:
                continue
            e = per.setdefault(ch, {"n": 0, "best": -128})
            e["n"] += 1
            e["best"] = max(e["best"], rssi)
    return per


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "zigscan/0.3.0"

    def log_message(self, fmt: str, *args) -> None:  # quieter console
        if "/api/job" not in (self.path or ""):
            sys.stderr.write(f"  {self.command} {self.path}\n")

    # -- helpers ----------------------------------------------------------
    def _json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _html(self, text: str) -> None:
        body = text.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n))
        except ValueError:
            return {}

    # -- routes -----------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802
        path = (self.path or "/").split("?")[0]
        if path == "/":
            return self._html(page())
        if path == "/api/state":
            return self._json(collect_state())
        if path == "/api/captures":
            return self._json({"captures": list_captures()})
        if path.startswith("/api/capture/"):
            rel = path[len("/api/capture/"):]
            target = (paths.DATA / rel).resolve()
            if not str(target).startswith(str(paths.DATA.resolve())) or not target.is_file():
                return self._json({"error": "not found", "error_code": "capture_not_found"}, 404)
            return self._json(decode_pcap(target))
        if path.startswith("/api/job/"):
            jid = path[len("/api/job/"):]
            since = 0
            if "?" in (self.path or ""):
                m = re.search(r"since=(\d+)", self.path)
                since = int(m.group(1)) if m else 0
            job = JOBS.get(jid)
            if not job:
                return self._json({"error": "no such job", "error_code": "job_not_found"}, 404)
            return self._json(job.snapshot(since))
        if path == "/api/jobs":
            return self._json({"jobs": [j.snapshot(10 ** 9) for j in JOBS.values()]})
        return self._json({"error": "not found", "error_code": "not_found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        path = (self.path or "/").split("?")[0]
        body = self._body()
        lang = body.get("lang", "es") if body.get("lang") in {"es", "en"} else "es"
        try:
            if path == "/api/scan":
                dwell = int(body.get("dwell", 6))
                if not 2 <= dwell <= 60:
                    return self._json({"error": "dwell must be 2-60 s",
                                       "error_code": "dwell_range"}, 400)
                # sys.executable, no bash: dentro de un .app empaquetado no hay
                # /bin/bash con un venv detrás, pero sí este mismo intérprete.
                job = start_job("scan", paths.worker_argv(str(dwell)), lang=lang)
                return self._json(job.snapshot())

            if path == "/api/sniff":
                ch = int(body.get("channel", 15))
                secs = int(body.get("seconds", 30))
                name = re.sub(r"[^A-Za-z0-9._-]", "", str(body.get("name", "")))[:60]
                if not 11 <= ch <= 26:
                    return self._json({"error": "channel must be 11-26",
                                       "error_code": "channel_range"}, 400)
                if not 5 <= secs <= 900:
                    return self._json({"error": "seconds must be 5-900",
                                       "error_code": "seconds_range"}, 400)
                name = name or f"console-{time.strftime('%Y%m%d-%H%M%S')}"
                job = start_job("capture",
                                paths.worker_argv("capture", str(ch), str(secs), name),
                                lang=lang)
                return self._json(job.snapshot())

            if path == "/api/flash":
                # Removed from the UI: the CatSniffer stays a permanent sniffer
                # (leaving its firmware needs SWD) and Home Assistant's radio is a
                # separate ZBDongle-E. Reflashing is still possible from the CLI
                # via tools/flash_cc1352.sh, but the console no longer offers it.
                return self._json({
                    "error": "role switching removed — the CatSniffer is a permanent "
                             "sniffer; use tools/flash_cc1352.sh from the CLI if you "
                             "really need to reflash",
                    "error_code": "role_switch_removed",
                }, 410)

            if path.startswith("/api/cancel/"):
                job = JOBS.get(path[len("/api/cancel/"):])
                if not job:
                    return self._json({"error": "no such job",
                                       "error_code": "job_not_found"}, 404)
                job.cancel()
                return self._json(job.snapshot(10 ** 9))
        except RuntimeError as exc:
            return self._json({"error": str(exc), "error_code": "job_busy"}, 409)
        except (TypeError, ValueError) as exc:
            return self._json({"error": f"bad request: {exc}",
                               "error_code": "bad_request"}, 400)

        return self._json({"error": "not found", "error_code": "not_found"}, 404)


_STATE_CACHE: dict = {"t": 0.0, "data": None}


def collect_state(max_age: float = 6.0) -> dict:
    """Live bench state. Cached briefly — the serial probe is slow and the UI polls."""
    now = time.time()
    if _STATE_CACHE["data"] and now - _STATE_CACHE["t"] < max_age:
        return _STATE_CACHE["data"]

    busy = any(j.status == "running" for j in JOBS.values())
    board = {"present": False, "port": None, "owner": None, "role": "unknown",
             "role_detail": "A job is using the radio — probe skipped.",
             "role_code": "radio_busy",
             "flashed_role": None, "flashed_at": None, "flashed_image": None}
    if busy:
        # Never open the serial port while a capture or flash owns it.
        rc, ioreg = lab_report.sh(["ioreg", "-p", "IOUSB", "-l", "-w", "0"], timeout=20)
        board["present"] = rc == 0 and "RaspberryPi Pico" in ioreg
        ports = sorted(pathlib.Path("/dev").glob("cu.usbmodem*"))
        board["port"] = str(ports[0]) if ports else None
        rec = paths.FIRMWARE / ".last_flash.json"
        if rec.is_file():
            try:
                j = json.loads(rec.read_text())
                board.update(flashed_role=j.get("role"), flashed_at=j.get("flashed_at"),
                             flashed_image=j.get("image"), role=j.get("role") or "unknown")
            except (ValueError, OSError):
                pass
    else:
        board = lab_report.probe_board()

    caps = [p for p in sorted(paths.CAPTURES.rglob("*.pcap"))
            if not p.name.endswith(".15p4.pcap")]

    data = {
        "board": board,
        "host": lab_report.probe_host(),
        "firmware": lab_report.probe_firmware(),
        "busy": busy,
        "jobs": [j.snapshot(10 ** 9) for j in
                 sorted(JOBS.values(), key=lambda x: -x.started)[:8]],
        "captures": list_captures()[:12],
        "spectrum": spectrum(),
        "scanned": scanned_channels(),
        # Both read the captures already on disk, so they cost no hardware time
        # and stay in the normal state poll.
        "census": census.census(caps),
        "verdict": {ch: dict(s, **verdict.verdict_for(s))
                    for ch, s in verdict.analyse(caps).items()},
        "wifi": _wifi_cached(),
        "now": time.strftime("%H:%M:%S"),
    }
    _STATE_CACHE.update(t=now, data=data)
    return data


def scanned_channels() -> dict:
    """Channels the most recent sweep actually listened to, and what it heard.

    Separate from spectrum(), which can only see channels that produced a
    capture. A channel measured and found silent leaves no pcap behind, so
    without this manifest it is indistinguishable from a channel nobody swept —
    and "we never listened there" must never be presented as "it is clear".
    """
    files = sorted(paths.CAPTURES.glob("scan-*.json"))
    if not files:
        return {}
    try:
        doc = json.loads(files[-1].read_text())
    except (ValueError, OSError):
        return {}
    return {int(k): v for k, v in (doc.get("channels") or {}).items()}


_WIFI_CACHE: dict = {"t": 0.0, "data": None, "running": False}


def _wifi_cached(max_age: float = 180.0) -> dict:
    """Wi-Fi scan, refreshed in the background.

    system_profiler takes several seconds, which is far too slow to sit inside a
    state poll the page makes every second. The first call starts a scan and
    returns "pending"; the answer appears on a later poll.
    """
    now = time.time()
    fresh = _WIFI_CACHE["data"] and now - _WIFI_CACHE["t"] < max_age
    if not fresh and not _WIFI_CACHE["running"]:
        _WIFI_CACHE["running"] = True

        def run() -> None:
            try:
                result = wifi.scan()
                result["recommend"] = wifi.recommend_wifi_24(result)
                _WIFI_CACHE.update(t=time.time(), data=result)
            finally:
                _WIFI_CACHE["running"] = False

        threading.Thread(target=run, daemon=True).start()

    return _WIFI_CACHE["data"] or {
        "ok": False, "note": "scanning…", "note_code": "scanning", "pending": True,
    }


# ---------------------------------------------------------------------------
# page
# ---------------------------------------------------------------------------
PAGE_FILE = paths.PAGE


def page() -> str:
    """The UI, read from disk on every request.

    Kept as a real .html file rather than a string inside this module: it is a
    designed artefact that someone edits with a browser open, and 400 lines of
    markup wedged into Python is how a UI stops getting improved. Re-read per
    request so a refresh is enough to see a change.
    """
    try:
        return PAGE_FILE.read_text()
    except OSError:
        return "<h1>tools/page.html is missing</h1>"



class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8477)
    ap.add_argument("--open", action="store_true", help="open a browser")
    args = ap.parse_args()

    # Bind loopback only. The console runs capture jobs and exposes local pcaps;
    # it must never be reachable from the network.
    srv = Server(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"\n  zigscan → {url}")
    print("  loopback only · Ctrl-C to stop\n")
    if args.open and shutil.which("open"):
        subprocess.Popen(["open", url])
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
