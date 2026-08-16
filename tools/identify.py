#!/usr/bin/env python3
"""Identify what firmware is on the CatSniffer — read-only.

Nothing here writes to flash. The board has two independently flashed chips
(RP2040 host MCU, CC1352P7 radio), so "what firmware is on it" is two questions,
and they are answered by different evidence:

  RP2040   USB descriptors, and INFO_UF2.TXT if it is in BOOTSEL mode.
  CC1352P7 Only reachable *through* the RP2040's serial passthrough, so it can
           only be probed once the RP2040 is running passthrough firmware.

Probe levels:
  --passive   (default) USB descriptors + mounted volumes only. Touches nothing.
  --probe     Additionally opens the serial port and listens for a banner, then
              optionally sends one Z-Stack SYS_VERSION request. That is ordinary
              application traffic, not bootloader traffic — it cannot brick the
              chip. Still opt-in, so a passive run is always safe.

Run:  ./.venv/bin/python tools/identify_catsniffer.py
      ./.venv/bin/python tools/identify_catsniffer.py --probe
"""

from __future__ import annotations

import argparse
import glob
import pathlib
import plistlib
import re
import subprocess
import sys

# ---------------------------------------------------------------------------
# Known USB signatures
# ---------------------------------------------------------------------------
# RP2040 in BOOTSEL exposes the Raspberry Pi vendor id with the RP2 Boot product
# id and mounts a mass-storage volume. Anything else on 0x2e8a is application
# firmware (Arduino sketch, CircuitPython, or Electronic Cats passthrough).
VID_RASPBERRY = 0x2E8A
PID_RP2_BOOT = 0x0003

RP2_BOOT_VOLUME = "RPI-RP2"


def sh(cmd: list[str]) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30).stdout
    except (subprocess.SubprocessError, OSError):
        return ""


def usb_devices() -> list[dict]:
    """Every USB device macOS currently sees, flattened.

    Uses ioreg, not `system_profiler SPUSBDataType`. system_profiler returns an
    empty USB tree under some sandboxed/managed execution contexts, which is
    indistinguishable from "nothing is plugged in" — it silently reported zero
    devices on this machine while ioreg listed all of them. ioreg reads the IO
    registry directly and does not have that failure mode.
    """
    raw = sh(["ioreg", "-p", "IOUSB", "-l", "-w", "0"])
    if not raw:
        return []

    devices: list[dict] = []
    current: dict | None = None

    for line in raw.splitlines():
        # A device node header, e.g. `+-o RaspberryPi Pico@02100000  <class ...`
        if "+-o " in line:
            if current and ("vendor_id" in current or "product_id" in current):
                devices.append(current)
            name = line.split("+-o ", 1)[1].split("<")[0].strip()
            current = {"_name": name.split("@")[0].strip()}
            continue
        if current is None:
            continue

        m = re.search(r'"(\w+)"\s*=\s*(.+?)\s*$', line)
        if not m:
            continue
        key, raw_val = m.group(1), m.group(2).rstrip(",")
        val = raw_val.strip('"')

        mapping = {
            "idVendor": "vendor_id",
            "idProduct": "product_id",
            "USB Vendor Name": "manufacturer",
            "USB Serial Number": "serial_num",
            "UsbExclusiveOwner": "exclusive_owner",
        }
        # ioreg prints the string keys with spaces, which the \w+ regex misses;
        # catch those separately.
        for ioreg_key, our_key in mapping.items():
            if f'"{ioreg_key}"' in line:
                current[our_key] = val
                break
        else:
            if key in ("bDeviceClass", "bcdDevice"):
                current[key] = val

    if current and ("vendor_id" in current or "product_id" in current):
        devices.append(current)
    return devices


def parse_id(value) -> int | None:
    """Parse a USB id that may be hex (`0x2e8a`) or plain decimal (`11914`).

    ioreg prints these in decimal; system_profiler printed them in hex. Handle
    both so the same code works regardless of source.
    """
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    m = re.search(r"0x([0-9a-fA-F]+)", text)
    if m:
        return int(m.group(1), 16)
    m = re.fullmatch(r"(\d+)", text)
    return int(m.group(1)) if m else None


def report_rp2040() -> str | None:
    """Identify the RP2040 side. Returns a serial port path if one exists."""
    print("=" * 72)
    print("RP2040 (host MCU / USB bridge)")
    print("=" * 72)

    # BOOTSEL mode leaves an INFO_UF2.TXT that names the board and bootloader.
    boot_vol = pathlib.Path("/Volumes") / RP2_BOOT_VOLUME
    if boot_vol.is_dir():
        print(f"  STATE: BOOTSEL (bootloader) — {boot_vol} is mounted")
        info = boot_vol / "INFO_UF2.TXT"
        if info.is_file():
            print("  INFO_UF2.TXT:")
            for line in info.read_text(errors="replace").splitlines():
                if line.strip():
                    print(f"    {line.strip()}")
        print()
        print("  => The RP2040 has NO application firmware running right now.")
        print("     Copy SerialPassthroughwithboot.uf2 into this volume to flash it.")
        print("     The CC1352P7 cannot be reached until that is done.")
        return None

    devices = usb_devices()
    if not devices:
        print("  STATE: nothing on USB at all — the board is not connected.")
        print()
        print("  Check, in this order:")
        print("    1. Is it plugged in?")
        print("    2. Is the USB-C cable a data cable? A charge-only cable")
        print("       enumerates nothing and looks exactly like a dead board.")
        print("    3. Try the other end / another port.")
        return None

    matches = []
    for d in devices:
        vid = parse_id(d.get("vendor_id"))
        pid = parse_id(d.get("product_id"))
        name = str(d.get("_name", "?"))
        vendor = str(d.get("manufacturer", ""))
        blob = f"{name} {vendor}".lower()
        if (
            vid == VID_RASPBERRY
            or "catsniffer" in blob
            or "electronic" in blob
            or "cats" in blob
            or "rp2" in blob
            or "pico" in blob
        ):
            matches.append(
                (name, vid, pid, vendor, d.get("serial_num"), d.get("exclusive_owner"))
            )

    if not matches:
        print(f"  STATE: {len(devices)} USB device(s) present, none look like a CatSniffer.")
        print("  Devices seen:")
        for d in devices:
            print(
                f"    {d.get('_name', '?')}  "
                f"vid={d.get('vendor_id')} pid={d.get('product_id')}"
            )
        return None

    stolen_by = None
    for name, vid, pid, vendor, serial_num, owner in matches:
        print(f"  DEVICE: {name}")
        print(f"    vendor id : {vid:#06x}" if vid else "    vendor id : ?")
        print(f"    product id: {pid:#06x}" if pid else "    product id: ?")
        if vendor:
            print(f"    vendor    : {vendor}")
        if serial_num:
            print(f"    serial    : {serial_num}")
        if vid == VID_RASPBERRY and pid == PID_RP2_BOOT:
            print("    => BOOTSEL mode (no application firmware)")
        elif vid == VID_RASPBERRY:
            print("    => application firmware running on the RP2040")
        if owner:
            print(f"    OWNER     : {owner}")
            stolen_by = owner
        print()

    if stolen_by:
        print("  *** DEVICE IS CLAIMED EXCLUSIVELY BY ANOTHER PROCESS ***")
        print(f"      {stolen_by}")
        if "prl_" in stolen_by:
            print()
            print("      Parallels has passed the board through to a VM, so macOS")
            print("      never bound its CDC-ACM driver and no /dev/cu.* node exists.")
            print("      This is not a board fault and not a cable fault.")
            print()
            print("      To use it from macOS (flashing, HA coordinator):")
            print("        Parallels menu bar -> Devices -> USB & Bluetooth")
            print("        -> click the Arduino / RaspberryPi Pico entry to release it.")
            print()
            print("      To use it from Windows (TI SmartRF Packet Sniffer 2):")
            print("        leave it connected to the VM — that is the right owner")
            print("        for the Phase 3 capture work. See docs/00-LAB-PLAN.md.")
        print()

    # Only cu.usbmodem* is ever the CatSniffer: the RP2040 is a native-USB CDC
    # device and macOS names those usbmodem. cu.usbserial* is a USB-UART bridge
    # (FTDI, CP210x, CH34x) — on a bench that is somebody else's radio, and
    # --probe *writes* to whatever this returns. Probing a live Zigbee
    # coordinator injects bytes into its serial stream, so those ports are
    # listed and left alone.
    ports = sorted(glob.glob("/dev/cu.usbmodem*"))
    others = sorted(glob.glob("/dev/cu.usbserial*"))
    if ports:
        print(f"  SERIAL PORTS: {', '.join(ports)}")
        print("  => A CDC serial port means the RP2040 is running application")
        print("     firmware. If that firmware is SerialPassthrough, this port")
        print("     reaches the CC1352P7.")
        if others:
            print(f"  OTHER RADIOS (not touched): {', '.join(others)}")
        return ports[0]

    print("  SERIAL PORTS: none")
    if others:
        print(f"  OTHER RADIOS (not touched): {', '.join(others)}")
        print("  => These are USB-UART bridges, not the CatSniffer. Pass one with")
        print("     --port only if you are certain nothing else is using it.")
    if stolen_by:
        print("  => Expected: another process owns the device (see above), so macOS")
        print("     never created a node. Release it and re-run — do NOT conclude")
        print("     anything about the firmware from this.")
    else:
        print("  => No CDC port. The RP2040 firmware is not exposing a serial bridge,")
        print("     so the CC1352P7 is unreachable until passthrough is flashed.")
    return None


def probe_cc1352(port: str) -> None:
    """Listen for a banner, then try one Z-Stack SYS_VERSION request."""
    import serial  # imported lazily so --passive needs no dependency

    print("=" * 72)
    print(f"CC1352P7 (radio) — probing via {port}")
    print("=" * 72)

    try:
        with serial.Serial(port, 115200, timeout=2) as ser:
            ser.reset_input_buffer()
            banner = ser.read(256)
            if banner:
                printable = banner.decode("ascii", errors="replace").strip()
                print(f"  UNSOLICITED OUTPUT ({len(banner)} bytes):")
                print(f"    {printable!r}")
                print("  => Some firmwares print a banner. Match it against the")
                print("     Electronic Cats firmware list.")
            else:
                print("  No unsolicited output (normal — most firmwares stay quiet).")

            # Z-Stack SYS_VERSION: SOF 0xFE, len 0x00, cmd 0x2102, FCS 0x23.
            # This is a standard application-level request. It is not a
            # bootloader command and cannot corrupt flash.
            print()
            print("  Sending Z-Stack SYS_VERSION (harmless application request)...")
            ser.reset_input_buffer()
            ser.write(bytes([0xFE, 0x00, 0x21, 0x02, 0x23]))
            ser.flush()
            reply = ser.read(64)

            if reply and reply[0:1] == b"\xfe":
                print(f"    reply: {reply.hex(' ')}")
                print("    => Looks like Z-Stack ZNP. This is COORDINATOR firmware.")
                if len(reply) >= 10:
                    print(
                        f"    transport={reply[5]} product={reply[6]} "
                        f"major={reply[7]} minor={reply[8]} maint={reply[9]}"
                    )
            elif reply:
                print(f"    reply: {reply.hex(' ')}")
                print("    => Responded, but not a ZNP frame. Probably TI sniffer")
                print("       firmware or something else. Not a coordinator.")
            else:
                print("    no reply.")
                print("    => Not Z-Stack. Most likely TI sniffer firmware (which")
                print("       speaks its own command set and ignores ZNP), or the")
                print("       RP2040 is not in passthrough mode.")
    except Exception as exc:  # noqa: BLE001
        print(f"  Could not open {port}: {type(exc).__name__}: {exc}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--probe",
        action="store_true",
        help="also open the serial port and send one harmless ZNP version request",
    )
    ap.add_argument("--port", help="serial port to probe (default: autodetect)")
    args = ap.parse_args()

    print()
    port = report_rp2040()
    print()

    target = args.port or port
    if args.probe:
        if target:
            probe_cc1352(target)
        else:
            print("Nothing to probe: no serial port available.")
    elif target:
        print(f"Re-run with --probe to interrogate the CC1352P7 through {target}.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
