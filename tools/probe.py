#!/usr/bin/env python3
"""Live hardware probes: what antenna is attached, and what is it running.

Every field the console shows about the bench comes from here, and every one of
them is measured at run time — board presence, USB ownership, firmware role,
capture inventory, host tooling. Nothing is hand-maintained, so the panel cannot
drift from what is actually plugged in.

The board probe only ever opens /dev/cu.usbmodem* (the CatSniffer's RP2040 CDC
port). USB-UART bridges — somebody else's coordinator — are never opened.

Imported by tools/console.py; not run directly.
"""

from __future__ import annotations

import glob
import json
import pathlib
import re
import struct
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paths  # noqa: E402
RPI_HEADER_LEN = 20


# ---------------------------------------------------------------------------
# probes
# ---------------------------------------------------------------------------
def sh(cmd: list[str], timeout: int = 60) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except (subprocess.SubprocessError, OSError):
        return 1, ""


def probe_host() -> dict:
    """Host tooling the lab depends on."""
    def have(name: str) -> bool:
        return sh(["command", "-v", name])[0] == 0 or bool(sh(["which", name])[1].strip())

    rc, tshark = sh(["tshark", "--version"], timeout=20)
    tshark_ver = ""
    if rc == 0:
        m = re.search(r"TShark \(Wireshark\) ([\d.]+)", tshark)
        tshark_ver = m.group(1) if m else "installed"

    rc, docker = sh(["docker", "--version"], timeout=20)
    docker_ver = docker.strip() if rc == 0 else ""

    return {
        "tshark": tshark_ver,
        "wireshark_app": pathlib.Path("/Applications/Wireshark.app").is_dir(),
        "docker": docker_ver,
        "socat": bool(sh(["socat", "-V"], timeout=10)[1].strip()),
        "wireshark_profile": (pathlib.Path.home() / ".config/wireshark/profiles/Control4").is_dir(),
    }


def probe_board() -> dict:
    """CatSniffer presence, ownership and which firmware the radio is running."""
    out = {
        "present": False, "port": None, "owner": None,
        "vid": None, "pid": None, "serial": None,
        "role": "unknown", "role_detail": "", "role_code": "",
        "flashed_role": None, "flashed_at": None, "flashed_image": None,
    }

    rc, ioreg = sh(["ioreg", "-p", "IOUSB", "-l", "-w", "0"], timeout=30)
    if rc == 0 and "RaspberryPi Pico" in ioreg:
        out["present"] = True
        block = ioreg.split("RaspberryPi Pico", 1)[1][:2500]
        for key, field in (("idVendor", "vid"), ("idProduct", "pid")):
            m = re.search(rf'"{key}" = (\d+)', block)
            if m:
                out[field] = f"0x{int(m.group(1)):04x}"
        m = re.search(r'"USB Serial Number" = "([^"]+)"', block)
        if m:
            out["serial"] = m.group(1)
        if "prl_vm_app" in block:
            out["owner"] = "Parallels VM"

    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    out["port"] = ports[0] if ports else None

    if not out["port"] or out["owner"]:
        out["role_code"] = "parallels" if out["owner"] else "no_serial"
        out["role_detail"] = (
            "Parallels holds the board — macOS has no serial node."
            if out["owner"] else "No serial port; radio unreachable."
        )
        return out

    # Identify the radio by who answers. The TI sniffer speaks its own framing at
    # 921600; Z-Stack answers SYS_VERSION with an 0xFE-framed reply.
    def ask(baud: int, frame: bytes, settle: float = 0.4, wait: float = 0.6) -> bytes:
        """Send one probe frame and return whatever comes back.

        The settle-after-open and wait-after-write are load-bearing: opening the
        CDC port makes the RP2040 re-init its UART, and reading immediately
        returns nothing even when the radio is alive. An earlier version of this
        probe skipped both and misreported working sniffer firmware as "unknown".
        """
        import time  # noqa: PLC0415

        import serial  # noqa: PLC0415

        with serial.Serial(out["port"], baud, timeout=3) as s:
            time.sleep(settle)
            s.reset_input_buffer()
            s.write(frame)
            s.flush()
            time.sleep(wait)
            return s.read(512)

    # What the flasher last wrote. Authoritative, because the radio cannot be
    # re-identified reliably after the fact: Z-Stack answers SYS_VERSION whenever
    # asked, but the TI sniffer firmware only answers a bare ping shortly after a
    # reset — so a silent port is ambiguous between "sniffer, idle" and "nothing
    # flashed". Recorded intent plus a live ZNP check is the honest combination.
    record = paths.FIRMWARE / ".last_flash.json"
    if record.is_file():
        try:
            rec = json.loads(record.read_text())
            out["flashed_role"] = rec.get("role")
            out["flashed_at"] = rec.get("flashed_at")
            out["flashed_image"] = rec.get("image")
        except (ValueError, OSError):
            pass

    try:
        # Z-Stack ZNP: SYS_VERSION, 0xFE-framed. This one is reliable on demand.
        znp = ask(115200, bytes([0xFE, 0x00, 0x21, 0x02, 0x23]))
        if znp[:1] == b"\xfe":
            out["role"] = "coordinator"
            out["role_code"] = "coordinator_live"
            out["role_detail"] = "Z-Stack ZNP — answers SYS_VERSION live."
            return out

        # TI sniffer answers its own '@S' ping, but only right after a reset.
        if b"\x40\x53" in ask(921600, bytes([0x40, 0x53, 0x40, 0x00, 0x00, 0x40, 0x40, 0x45])):
            out["role"] = "sniffer"
            out["role_code"] = "sniffer_live"
            out["role_detail"] = "TI sniffer firmware — answered the @S ping live."
            return out

        if out["flashed_role"]:
            out["role"] = out["flashed_role"]
            out["role_code"] = "last_flashed"
            out["role_detail"] = (
                f"Last flashed {out['flashed_role']} ({out['flashed_image']}) on "
                f"{out['flashed_at']}. Idle — no live ping answer, which is normal for "
                "the TI sniffer once it has been started and stopped. Capture still works."
            )
        else:
            out["role"] = "unknown"
            out["role_code"] = "no_probe_answer"
            out["role_detail"] = (
                "No live ping answer and no flash on record. Run a capture to test "
                "functionally, or reflash."
            )
    except Exception as exc:  # noqa: BLE001
        out["role_code"] = "probe_failed"
        out["role_detail"] = f"probe failed: {type(exc).__name__}: {exc}"

    return out

def probe_captures() -> dict:
    """Frames actually captured, by channel, with signal strength."""
    per_channel: dict[int, dict] = {}
    files = 0
    for path in sorted(paths.CAPTURES.rglob("*.pcap")):
        if path.name.endswith(".15p4.pcap"):
            continue
        data = path.read_bytes()
        if len(data) < 24:
            continue
        magic, *_rest, link = struct.unpack("<LHHIILL", data[:24])
        if magic != 0xA1B2C3D4 or link != 147:
            continue
        files += 1
        off = 24
        while off + 16 <= len(data):
            _ts, _us, caplen, _ol = struct.unpack("<llll", data[off : off + 16])
            if caplen < 0 or off + 16 + caplen > len(data):
                break
            rec = data[off + 16 : off + 16 + caplen]
            off += 16 + caplen
            if len(rec) < RPI_HEADER_LEN:
                continue
            ch = struct.unpack("<H", rec[12:14])[0]
            rssi = struct.unpack("<b", rec[14:15])[0]
            paylen = rec[19]
            frame = rec[RPI_HEADER_LEN : RPI_HEADER_LEN + paylen]
            if not frame or len(frame) < 3:
                continue
            fcf = struct.unpack("<H", frame[:2])[0]
            kind = "Beacon Request" if (fcf & 0x7) == 3 and len(frame) >= 8 and frame[7] == 0x07 \
                else {0: "Beacon", 1: "Data", 2: "ACK", 3: "MAC-Cmd"}.get(fcf & 0x7, "other")
            e = per_channel.setdefault(ch, {"n": 0, "best": -128, "kinds": {}})
            e["n"] += 1
            e["best"] = max(e["best"], rssi)
            e["kinds"][kind] = e["kinds"].get(kind, 0) + 1
    return {"files": files, "channels": per_channel}


def probe_firmware() -> list[dict]:
    out = []
    for p in sorted(paths.FIRMWARE.glob("*")):
        if p.suffix.lower() not in (".hex", ".uf2"):
            continue
        role = {
            "sniffer_fw": ("CC1352P7", "TI sniffer — 802.15.4 capture"),
            "CC1352P7_coordinator": ("CC1352P7", "Z-Stack ZNP coordinator for ZHA"),
            "SerialPassthroughwithboot": ("RP2040", "USB↔CC1352 bridge + bootloader entry"),
            "free_dap": ("RP2040", "CMSIS-DAP probe — brick recovery"),
        }
        target, desc = ("?", "")
        for key, (t, d) in role.items():
            if p.name.startswith(key):
                target, desc = t, d
                break
        out.append({"name": p.name, "kb": p.stat().st_size // 1024,
                    "target": target, "desc": desc})
    return out
