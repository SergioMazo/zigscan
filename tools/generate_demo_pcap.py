#!/usr/bin/env python3
"""Generate the public ZigScan demo PCAP without using captured RF traffic.

The frames are deterministic synthetic IEEE 802.15.4 data. PAN identifiers,
locally administered EUI-64 values and encrypted-looking payload bytes are
generated from a fixed demo seed and have no relationship to a real network.
"""

from __future__ import annotations

import pathlib
import random
import struct
import sys

CHANNEL = 15
FREQUENCY_MHZ = 2425
DEMO_SEED = 0x5A1F2026
BASE_TIMESTAMP = 1767225600  # 2026-01-01 00:00:00 UTC


def fcs(payload: bytes) -> bytes:
    """IEEE 802.15.4 CRC-16, stored least-significant byte first."""
    crc = 0
    for byte in payload:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return struct.pack("<H", crc & 0xFFFF)


def frame(payload: bytes) -> bytes:
    return payload + fcs(payload)


def local_eui(rng: random.Random) -> bytes:
    """A locally administered unicast EUI-64, in display byte order."""
    value = bytearray(rng.getrandbits(8) for _ in range(8))
    value[0] = (value[0] | 0x02) & 0xFE
    return bytes(value)


def rpi_record(packet: bytes, rssi: int, index: int) -> bytes:
    """Wrap one frame in the 20-byte CatSniffer Radio Packet Info header."""
    header = bytearray(20)
    header[:8] = bytes.fromhex("0015000003000203")
    header[8:12] = struct.pack("<I", FREQUENCY_MHZ)
    header[12:14] = struct.pack("<H", CHANNEL)
    header[14] = rssi & 0xFF
    header[15] = 0x80  # FCS accepted by the receiver
    header[16:19] = index.to_bytes(3, "little")
    header[19] = len(packet)
    return bytes(header) + packet


def build_frames() -> list[tuple[bytes, int]]:
    rng = random.Random(DEMO_SEED)
    pan = rng.randrange(1, 0xFFFF)
    coordinator = local_eui(rng)
    device = local_eui(rng)
    ext_pan = local_eui(rng)
    synthetic_ciphertext = bytes(rng.getrandbits(8) for _ in range(24))
    coordinator_short = 0x0000
    device_short = 0x4A31

    def beacon(seq: int) -> bytes:
        fcf_value = 3 << 14  # beacon, extended source address
        superframe = 0xCFFF  # PAN coordinator; association permitted
        network_info = 0x8402  # Zigbee PRO, router/end-device capacity
        zigbee_payload = (
            b"\x00" + struct.pack("<H", network_info) + ext_pan[::-1]
            + b"\xff\xff\xff" + b"\x01"
        )
        body = (
            struct.pack("<HBH", fcf_value, seq, pan) + coordinator[::-1]
            + struct.pack("<HBB", superframe, 0, 0) + zigbee_payload
        )
        return frame(body)

    def long_command(seq: int, source: bytes, destination: bytes,
                     source_pan: int, command: bytes,
                     pan_compression: bool = False) -> bytes:
        fcf_value = 3 | 0x20 | (3 << 10) | (3 << 14)
        if pan_compression:
            fcf_value |= 0x40
        body = struct.pack("<HBH", fcf_value, seq, pan) + destination[::-1]
        if not pan_compression:
            body += struct.pack("<H", source_pan)
        body += source[::-1] + command
        return frame(body)

    def ack(seq: int) -> bytes:
        return frame(struct.pack("<HB", 0x0002, seq))

    def short_data(seq: int, secured: bool) -> bytes:
        fcf_value = 1 | 0x20 | 0x40 | (2 << 10) | (2 << 14)
        body = struct.pack("<HBHHH", fcf_value | (0x08 if secured else 0),
                           seq, pan, coordinator_short, device_short)
        if secured:
            # Auxiliary security header followed by arbitrary demo ciphertext.
            body += b"\x05" + struct.pack("<I", seq) + b"\x01"
            body += synthetic_ciphertext
        else:
            body += bytes(rng.getrandbits(8) for _ in range(18))
        return frame(body)

    packets = [
        (beacon(1), -46),
        (long_command(2, device, coordinator, 0xFFFF, b"\x01\x8e"), -55),
        (ack(2), -47),
        (long_command(3, coordinator, device, pan,
                      b"\x02" + struct.pack("<HB", device_short, 0), True), -47),
        (ack(3), -55),
        (long_command(4, device, coordinator, pan, b"\x04", True), -54),
        (ack(4), -47),
        (short_data(5, True), -53),
        (ack(5), -47),
        (short_data(6, False), -52),
        (ack(6), -47),
        (beacon(7), -48),
        (long_command(8, device, coordinator, pan, b"\x04", True), -56),
        (ack(8), -48),
        (short_data(9, True), -54),
        (ack(9), -48),
        (short_data(10, False), -51),
        (ack(10), -48),
    ]
    return packets


def generate(destination: pathlib.Path) -> None:
    output = bytearray(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0,
                                   65535, 147))
    for index, (packet, rssi) in enumerate(build_frames()):
        record = rpi_record(packet, rssi, index)
        output += struct.pack("<IIII", BASE_TIMESTAMP + index, index * 1000,
                              len(record), len(record))
        output += record
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(output)


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    destination = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else (
        root / "samples" / "demo-synthetic-join.pcap"
    )
    generate(destination)
    print(f"wrote {len(build_frames())} synthetic frames to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
