#!/usr/bin/env python3
"""Convert a CatSniffer pcap (linktype 147) to standard IEEE 802.15.4 pcap.

pycatsniffer writes linktype 147 (USER0) records wrapped in TI's Radio Packet
Info header, which only Electronic Cats' bundled dissectors understand — and
their compiled dissector is built for Wireshark 4.4.0, so it will not load on a
newer Wireshark. Stripping the header and rewriting as linktype 195
(IEEE802_15_4_WITHFCS) makes captures readable by *any* current tshark or
Wireshark, plus zbee dissectors, with no plugins at all.

Record layout, derived from SnifferCollector.py's packet construction and
confirmed byte-for-byte against real captures:

    off  size  field
      0     1  version
      1     2  packet_length (LE)
      3     1  interfaceType
      4     2  interfaceId (LE)
      6     1  protocol
      7     1  phy
      8     4  frequency in MHz (LE)      e.g. 2415 for channel 13
     12     2  channel (LE)
     14     1  rssi (signed)
     15     1  status                     0x80 = FCS/CRC OK
     16     2  connect_evt
     18     1  conn_info
     19     1  payload length
     20     n  802.15.4 frame, FCS included

Run:  ./.venv/bin/python tools/pcap_convert.py in.pcap [out.pcap]
"""

from __future__ import annotations

import pathlib
import struct
import sys

LINKTYPE_USER0 = 147
LINKTYPE_IEEE802_15_4_WITHFCS = 195

RPI_HEADER_LEN = 20  # through the payload-length byte

FRAME_TYPES = {0: "Beacon", 1: "Data", 2: "ACK", 3: "MAC-Command"}
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


def global_header(linktype: int) -> bytes:
    return struct.pack("<LHHIILL", 0xA1B2C3D4, 2, 4, 0, 0, 0xFFFF, linktype)


def describe(frame: bytes) -> str:
    """One-line human summary of an 802.15.4 frame."""
    if len(frame) < 3:
        return f"runt ({len(frame)} bytes)"
    fcf = struct.unpack("<H", frame[:2])[0]
    ftype = FRAME_TYPES.get(fcf & 0x7, f"type{fcf & 0x7}")
    seq = frame[2]
    bits = [f"{ftype} seq={seq}"]
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
            bits.append(MAC_COMMANDS.get(command, f"cmd 0x{command:02x}"))
    return "  ".join(bits)


def convert(src: pathlib.Path, dst: pathlib.Path) -> int:
    data = src.read_bytes()
    if len(data) < 24:
        print(f"  {src.name}: too short to be a pcap")
        return 1

    magic, _vM, _vm, _tz, _sig, _snap, link = struct.unpack("<LHHIILL", data[:24])
    if magic != 0xA1B2C3D4:
        print(f"  {src.name}: not a little-endian pcap")
        return 1
    if link != LINKTYPE_USER0:
        print(f"  {src.name}: linktype is {link}, not {LINKTYPE_USER0} — nothing to convert")
        return 1

    out = bytearray(global_header(LINKTYPE_IEEE802_15_4_WITHFCS))
    off = 24
    kept = skipped = 0

    print(f"  {src.name}")
    while off + 16 <= len(data):
        ts, us, caplen, _orig = struct.unpack("<llll", data[off : off + 16])
        rec = data[off + 16 : off + 16 + caplen]
        off += 16 + caplen

        if len(rec) < RPI_HEADER_LEN:
            skipped += 1
            continue

        freq = struct.unpack("<I", rec[8:12])[0]
        channel = struct.unpack("<H", rec[12:14])[0]
        rssi = struct.unpack("<b", rec[14:15])[0]
        status = rec[15]
        paylen = rec[19]
        frame = rec[RPI_HEADER_LEN : RPI_HEADER_LEN + paylen]

        if not frame:
            skipped += 1
            continue

        fcs_ok = "FCS-ok" if status & 0x80 else f"status=0x{status:02x}"
        print(
            f"    ch{channel:<3} {freq} MHz  {rssi:>4} dBm  {fcs_ok:<12} "
            f"{len(frame):>3}B  {describe(frame)}"
        )

        out += struct.pack("<llll", ts, us, len(frame), len(frame)) + frame
        kept += 1

    dst.write_bytes(bytes(out))
    print()
    print(f"  => {kept} frames written to {dst}" + (f", {skipped} skipped" if skipped else ""))
    print(f"     linktype {LINKTYPE_IEEE802_15_4_WITHFCS} (IEEE802_15_4_WITHFCS) — reads in any Wireshark")
    return 0


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    src = pathlib.Path(sys.argv[1])
    if not src.is_file():
        print(f"not found: {src}")
        return 1
    dst = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".15p4.pcap")
    return convert(src, dst)


if __name__ == "__main__":
    sys.exit(main())
