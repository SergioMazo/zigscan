#!/usr/bin/env python3
"""Summarise a CatSniffer pcap: how many frames, from how far, and what kind.

Handles both formats:
  linktype 147  pycatsniffer's native output — TI Radio Packet Info header
                wrapping the 802.15.4 frame. Carries channel, frequency and RSSI,
                which is why it is worth reading rather than converting away.
  linktype 195  already converted by tools/pcap_convert.py.

RSSI is the most useful column here. A Control4 device on the bench reads around
-40 dBm; anything near -90 dBm is a distant network, not our hardware, and should
not be mistaken for the device under test.

Run:  ./.venv/bin/python tools/pcap_summary.py <file.pcap> [...]
"""

from __future__ import annotations

import pathlib
import struct
import sys

LINKTYPE_USER0 = 147
LINKTYPE_IEEE802_15_4_WITHFCS = 195

LINKTYPE_NAMES = {
    LINKTYPE_USER0: "USER0 (CatSniffer RPI records)",
    LINKTYPE_IEEE802_15_4_WITHFCS: "IEEE802_15_4_WITHFCS",
    215: "IEEE802_15_4_NONASK_PHY",
    230: "IEEE802_15_4_NOFCS",
    256: "BLUETOOTH_LE_LL_WITH_PHDR",
}

RPI_HEADER_LEN = 20

# 0-3 are the classic 802.15.4-2003 types; 4-7 only exist in 802.15.4e and are
# reserved otherwise, so seeing them usually means noise or a non-Zigbee radio.
FRAME_TYPES = {
    0: "Beacon",
    1: "Data",
    2: "ACK",
    3: "MAC-Command",
    4: "reserved-4",
    5: "Multipurpose",
    6: "Fragment/Frak",
    7: "Extended",
}
MAC_COMMANDS = {
    0x01: "Association Request",
    0x02: "Association Response",
    0x03: "Disassociation Notification",
    0x04: "Data Request",
    0x05: "PAN ID Conflict",
    0x06: "Orphan Notification",
    0x07: "Beacon Request",
    0x08: "Coordinator Realignment",
    0x09: "GTS Request",
}


def classify(frame: bytes) -> str:
    if len(frame) < 3:
        return f"runt({len(frame)}B)"
    fcf = struct.unpack("<H", frame[:2])[0]
    label = FRAME_TYPES.get(fcf & 0x7, f"type{fcf & 0x7}")
    if (fcf & 0x7) == 3:
        dst_mode = (fcf >> 10) & 0x3
        src_mode = (fcf >> 14) & 0x3
        i = 3
        if dst_mode:
            i += 2 + (2 if dst_mode == 2 else 8)
        if src_mode:
            if not (dst_mode and fcf & 0x40):
                i += 2
            i += 2 if src_mode == 2 else 8
        if i < len(frame) - 2:
            command = frame[i]
            return f"{label}: {MAC_COMMANDS.get(command, f'cmd 0x{command:02x}')}"
    return label


def records(data: bytes) -> list[tuple[bytes, int | None, int | None, int | None]]:
    """Yield (frame, channel, rssi, status). channel/rssi are None on linktype 195."""
    _magic, _vM, _vm, _tz, _sig, _snap, link = struct.unpack("<LHHIILL", data[:24])
    out = []
    off = 24
    while off + 16 <= len(data):
        _ts, _us, caplen, _orig = struct.unpack("<llll", data[off : off + 16])
        if caplen < 0 or off + 16 + caplen > len(data):
            break
        rec = data[off + 16 : off + 16 + caplen]
        off += 16 + caplen

        if link == LINKTYPE_USER0:
            if len(rec) < RPI_HEADER_LEN:
                continue
            channel = struct.unpack("<H", rec[12:14])[0]
            rssi = struct.unpack("<b", rec[14:15])[0]
            status = rec[15]
            paylen = rec[19]
            frame = rec[RPI_HEADER_LEN : RPI_HEADER_LEN + paylen]
            if frame:
                out.append((frame, channel, rssi, status))
        else:
            out.append((rec, None, None, None))
    return out


def summarise(path: pathlib.Path) -> int:
    data = path.read_bytes()
    if len(data) < 24:
        print(f"  {path.name}: too short to be a pcap ({len(data)} bytes)")
        return 1

    magic, v_major, v_minor, _tz, _sig, snaplen, link = struct.unpack("<LHHIILL", data[:24])
    if magic != 0xA1B2C3D4:
        print(f"  {path.name}: not a little-endian pcap (magic {magic:#010x})")
        return 1

    print(f"  {path.name}")
    print(f"    pcap v{v_major}.{v_minor}  snaplen={snaplen}  "
          f"linktype {link} — {LINKTYPE_NAMES.get(link, 'unknown')}")

    recs = records(data)
    if not recs:
        print("    => 0 frames")
        return 0

    counts: dict[str, int] = {}
    for frame, _ch, _rssi, _st in recs:
        label = classify(frame)
        counts[label] = counts.get(label, 0) + 1

    print(f"    => {len(recs)} frames")
    for label, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"         {count:>5}  {label}")

    rssis = [r for _f, _c, r, _s in recs if r is not None]
    chans = sorted({c for _f, c, _r, _s in recs if c is not None})
    if rssis:
        near = sum(1 for r in rssis if r > -60)
        print(f"       RSSI: min={min(rssis)} max={max(rssis)} dBm"
              f"   ({near} of {len(rssis)} stronger than -60 dBm = on the bench)")
    if chans:
        print(f"       channels: {', '.join(str(c) for c in chans)}")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    rc = 0
    for arg in sys.argv[1:]:
        p = pathlib.Path(arg)
        if not p.is_file():
            print(f"  {arg}: not found")
            rc = 1
            continue
        rc |= summarise(p)
    return rc


if __name__ == "__main__":
    sys.exit(main())
