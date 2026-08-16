#!/usr/bin/env python3
"""Who is already on the air here — a census of the 802.15.4 networks in range.

A spectrum reading tells you a channel is busy. This tells you *what* is on it:
how many networks, which brands, whether any of them is sitting with the door
open for new devices, and whether they are standard Zigbee or somebody's
proprietary stack on the same radio.

Two independent sources, because neither is enough alone:

  BEACONS carry the network's identity — PAN ID, permit-join flag, stack
  profile, depth. They are authoritative but rare: an idle network beacons
  seldom, so a short capture can miss one entirely.

  DEVICE ADDRESSES carry the brand. Every 64-bit address on the air starts with
  the manufacturer's OUI, so the traffic itself says who built the hardware —
  even on a channel where no beacon was ever captured.

The extended PAN ID is deliberately *not* used for brand detection. Many
coordinators generate it at random rather than deriving it from a MAC — Home
Assistant's ZHA does exactly that — so reading a vendor out of it produces
confident nonsense.

Completely passive. No beacon request is transmitted; nothing is asked of the
customer's network. A beacon request would enumerate everything in seconds, but
it means transmitting into a system you were hired to measure, and the survey
firmware cannot transmit anyway.

Run:  ./zigscan census [capture.pcap ...]
"""

from __future__ import annotations

import pathlib
import struct
import sys

RPI_HEADER_LEN = 20

# Stack profile from the Zigbee beacon payload. 0 means the network follows no
# published profile — proprietary. Control4 is the vendor this tool was born
# from, but it is not the only one that does it.
STACK_PROFILES = {0: "proprietary", 1: "Zigbee 2006/2007", 2: "Zigbee PRO"}

# OUI -> (vendor, confirmed-on-real-hardware).
#
# Only entries marked True have been seen on this bench against known hardware.
# The rest come from public OUI assignments and are reported with a "?" until
# somebody confirms them in the field: a wrong brand stated confidently in front
# of a customer is worse than no brand at all.
#
# Extend this list as you meet hardware — it is the part of the tool that gets
# better with use.
OUI_VENDORS = {
    # Confirmed on this bench against known hardware.
    "00:0f:ff": ("Control4", True),            # SR260 remote
    "94:a0:81": ("SONOFF / ITead", True),      # ZBDongle-E coordinator
    "f0:44:d3": ("SONOFF / ITead", True),      # ZBMINI-L2 switch
    # From public OUI assignments, not yet seen in the field.
    "00:17:88": ("Philips Hue / Signify", False),
    "00:12:4b": ("Texas Instruments module", False),
    "00:0d:6f": ("Ember / Silicon Labs", False),
    "00:15:8d": ("Xiaomi / Aqara", False),
    "68:0a:e2": ("Samsung SmartThings", False),
}


def _addr(b: bytes) -> str:
    return ":".join(f"{x:02x}" for x in reversed(b))


def vendor_for(mac: str) -> tuple[str, bool]:
    """Vendor from a 64-bit address. Returns (name, confirmed)."""
    if not mac or len(mac.split(":")) != 8:
        return ("", False)
    oui = ":".join(mac.split(":")[:3])
    return OUI_VENDORS.get(oui, ("", False))


def parse_addressing(frame: bytes) -> dict:
    """MHR addressing fields: PAN IDs and any 64-bit addresses.

    Deliberately parsed rather than pattern-matched. Scanning a frame for
    byte sequences that look like a known OUI finds them inside payloads and
    encrypted data too, and invents devices that are not there.
    """
    out = {"src_pan": None, "dst_pan": None, "long": []}
    if len(frame) < 3:
        return out
    fcf = struct.unpack("<H", frame[:2])[0]
    dst_mode = (fcf >> 10) & 0x3
    src_mode = (fcf >> 14) & 0x3
    pan_compression = bool(fcf & 0x40)

    i = 3
    try:
        if dst_mode:
            out["dst_pan"] = struct.unpack("<H", frame[i : i + 2])[0]
            i += 2
            if dst_mode == 2:
                i += 2
            elif dst_mode == 3:
                out["long"].append(_addr(frame[i : i + 8]))
                i += 8
        if src_mode:
            if not (dst_mode and pan_compression):
                out["src_pan"] = struct.unpack("<H", frame[i : i + 2])[0]
                i += 2
            elif dst_mode:
                out["src_pan"] = out["dst_pan"]
            if src_mode == 2:
                i += 2
            elif src_mode == 3:
                out["long"].append(_addr(frame[i : i + 8]))
                i += 8
    except (struct.error, IndexError):
        pass
    return out


def parse_beacon(frame: bytes) -> dict | None:
    """Network identity out of one 802.15.4 beacon. None if not a beacon."""
    if len(frame) < 5:
        return None
    fcf = struct.unpack("<H", frame[:2])[0]
    if (fcf & 0x7) != 0:
        return None

    dst_mode = (fcf >> 10) & 0x3
    src_mode = (fcf >> 14) & 0x3
    pan_compression = bool(fcf & 0x40)

    i = 3
    try:
        if dst_mode:
            i += 2
            i += 2 if dst_mode == 2 else 8

        src_pan = None
        if src_mode:
            if not (dst_mode and pan_compression):
                src_pan = struct.unpack("<H", frame[i : i + 2])[0]
                i += 2
            i += 2 if src_mode == 2 else 8

        superframe = struct.unpack("<H", frame[i : i + 2])[0]
        i += 2
        gts = frame[i]
        i += 1
        gts_count = gts & 0x7
        if gts_count:
            i += gts_count * 3 + 1
        pending = frame[i]
        i += 1
        i += (pending & 0x7) * 2
        i += ((pending >> 4) & 0x7) * 8

        out = {
            "pan": f"0x{src_pan:04x}" if src_pan is not None else "",
            "permit_join": bool(superframe & 0x8000),
            "ext_pan": "", "stack_profile": None,
            "router_capacity": None, "depth": None, "zigbee": False,
            "payload_len": 0,
        }

        # Zigbee beacon payload, 15 bytes. Its absence means 802.15.4 that is not
        # Zigbee — other vendor stacks build on the same PHY and MAC.
        rest = frame[i:-2] if len(frame) > i + 2 else b""
        out["payload_len"] = len(rest)
        if len(rest) >= 15 and rest[0] == 0x00:
            info = struct.unpack("<H", rest[1:3])[0]
            out.update({
                "zigbee": True,
                "stack_profile": info & 0xF,
                "router_capacity": bool(info & 0x0400),
                "depth": (info >> 11) & 0xF,
                "ext_pan": _addr(rest[3:11]),
            })
        return out
    except (struct.error, IndexError):
        return None


def scan_file(path: pathlib.Path) -> tuple[list[dict], list[dict], list[dict]]:
    """(beacons, device sightings, per-frame traffic) from one capture.

    Traffic is the third source and the one that works on a network nobody is
    touching. A settled Zigbee network addresses everything with 16-bit NWK
    addresses, so no OUI is on the air and no beacon is sent — but the PAN ID
    rides in every frame. That is enough to say "there is a network here, on
    this channel", which is most of what a survey needs.
    """
    data = path.read_bytes()
    if len(data) < 24:
        return [], [], []
    magic, *_rest, link = struct.unpack("<LHHIILL", data[:24])
    if magic != 0xA1B2C3D4:
        return [], [], []

    beacons: list[dict] = []
    sightings: list[dict] = []
    traffic: list[dict] = []
    off = 24
    while off + 16 <= len(data):
        _ts, _us, caplen, _orig = struct.unpack("<llll", data[off : off + 16])
        rec = data[off + 16 : off + 16 + caplen]
        off += 16 + caplen
        if caplen < 0:
            break

        ch = rssi = None
        if link == 147:
            if len(rec) < RPI_HEADER_LEN:
                continue
            # Byte 15 bit 7 is the radio's own CRC verdict. A frame that failed
            # it is noise that happens to parse: its addresses and even its
            # frame type are unreliable, and one of them decoding as a beacon
            # would put a network on the report that does not exist.
            if not rec[15] & 0x80:
                continue
            ch = struct.unpack("<H", rec[12:14])[0]
            rssi = struct.unpack("<b", rec[14:15])[0]
            frame = rec[RPI_HEADER_LEN : RPI_HEADER_LEN + rec[19]]
        else:
            frame = rec
        if len(frame) < 3:
            continue

        b = parse_beacon(frame)
        if b:
            b["channel"], b["rssi"] = ch, rssi
            beacons.append(b)

        addr = parse_addressing(frame)
        pan = None
        for candidate in (addr["src_pan"], addr["dst_pan"]):
            # 0xffff is the broadcast PAN, not an identity.
            if candidate is not None and candidate != 0xFFFF:
                pan = candidate
                break
        traffic.append({
            "channel": ch, "rssi": rssi,
            "pan": f"0x{pan:04x}" if pan is not None else "",
            "identified": bool(b) or pan is not None,
        })

        for mac in addr["long"]:
            name, confirmed = vendor_for(mac)
            if name:
                sightings.append({
                    "mac": mac, "vendor": name, "confirmed": confirmed,
                    "channel": ch, "rssi": rssi,
                    "pan": f"0x{addr['src_pan']:04x}" if addr["src_pan"] is not None else "",
                })
    return beacons, sightings, traffic


def census(paths: list[pathlib.Path], with_unattributed: bool = False):
    """One row per network, merging beacon identity with device brands."""
    nets: dict[tuple, dict] = {}
    all_sightings: list[dict] = []
    all_traffic: list[dict] = []

    for p in paths:
        beacons, sightings, traffic = scan_file(p)
        all_sightings.extend(sightings)
        all_traffic.extend(traffic)
        for b in beacons:
            key = (b["channel"], b["pan"])
            row = nets.get(key)
            if row is None:
                row = {
                    "channel": b["channel"], "pan": b["pan"], "ext_pan": b["ext_pan"],
                    "beacons": 0, "best_rssi": -128, "permit_join": False,
                    "zigbee": b["zigbee"], "stack_profile": b["stack_profile"],
                    "router_capacity": b["router_capacity"], "depth": b["depth"],
                    "payload_len": b["payload_len"], "vendors": {}, "devices": set(),
                    "from_beacon": True,
                }
                nets[key] = row
            row["beacons"] += 1
            if b["rssi"] is not None:
                row["best_rssi"] = max(row["best_rssi"], b["rssi"])
            # Permit-join is a moment, not a property. If it was ever open during
            # the capture, that is what the technician needs to hear about.
            row["permit_join"] = row["permit_join"] or b["permit_join"]

    # Brands, attached to the network they were talking on. A channel with device
    # traffic but no captured beacon still gets a row — that is a real network,
    # just a quiet one, and leaving it out would be the same lie as saying the
    # channel is free.
    for s in all_sightings:
        # 0xffff is the broadcast PAN a device uses before it belongs to a
        # network — during a join, or when orphaned. It is not a network, and
        # listing it as one invents a second system that does not exist.
        if s["pan"] == "0xffff":
            s = dict(s, pan="")

        key = (s["channel"], s["pan"])
        if key not in nets:
            # Same radio, same channel, already accounted for: a device that also
            # appears inside a known network is that network's device, not a
            # second system. This is what a join looks like — the device talks on
            # the broadcast PAN first and its own PAN afterwards.
            known = [k for k, v in nets.items()
                     if k[0] == s["channel"] and s["mac"] in v["devices"]]
            if known:
                key = known[0]
            else:
                # An address with no PAN of its own belongs to the network on
                # that channel, when there is exactly one to belong to.
                loose = [k for k in nets if k[0] == s["channel"] and k[1]]
                if len(loose) == 1 and not s["pan"]:
                    key = loose[0]
            if key not in nets:
                nets[key] = {
                    "channel": s["channel"], "pan": s["pan"], "ext_pan": "",
                    "beacons": 0, "best_rssi": -128, "permit_join": False,
                    "zigbee": None, "stack_profile": None, "router_capacity": None,
                    "depth": None, "payload_len": 0, "vendors": {}, "devices": set(),
                    "from_beacon": False,
                }
        row = nets[key]
        row["vendors"][s["vendor"]] = s["confirmed"]
        row["devices"].add(s["mac"])
        if s["rssi"] is not None:
            row["best_rssi"] = max(row["best_rssi"], s["rssi"])

    # Networks visible only through their ordinary traffic. No beacon, no OUI —
    # just a PAN ID repeating on a channel, which is exactly what a settled
    # network looks like. Counting these is the difference between "no network
    # here" and "a network I could not name".
    for t in all_traffic:
        if not t["pan"]:
            continue
        key = (t["channel"], t["pan"])
        row = nets.get(key)
        if row is None:
            row = nets[key] = {
                "channel": t["channel"], "pan": t["pan"], "ext_pan": "",
                "beacons": 0, "best_rssi": -128, "permit_join": False,
                "zigbee": None, "stack_profile": None, "router_capacity": None,
                "depth": None, "payload_len": 0, "vendors": {}, "devices": set(),
                "from_beacon": False, "frames": 0,
            }
        row["frames"] = row.get("frames", 0) + 1
        if t["rssi"] is not None:
            row["best_rssi"] = max(row["best_rssi"], t["rssi"])

    # Frames that carried no identity at all: no PAN, no beacon. Reported as a
    # count rather than dropped, so "I heard things I could not attribute" never
    # gets rendered as silence.
    unattributed = sum(1 for t in all_traffic if not t["identified"])

    # Fold the PAN-less rows into the network that owns the same device. During a
    # join a device talks on the broadcast PAN before it talks on its own, and
    # the two sightings arrive in that order — so this cannot be decided while
    # walking the frames, only afterwards.
    for key in [k for k in list(nets) if not k[1]]:
        orphan = nets[key]
        home = next((k for k, v in nets.items()
                     if k is not key and k[0] == key[0] and k[1]
                     and orphan["devices"] & v["devices"]), None)
        if home:
            nets[home]["devices"] |= orphan["devices"]
            nets[home]["vendors"].update(orphan["vendors"])
            nets[home]["best_rssi"] = max(nets[home]["best_rssi"], orphan["best_rssi"])
            del nets[key]

    # Una sola trama no es una red. El PAN sale de un campo de dos bytes: basta
    # un frame mal alineado o de otra tecnologia para que aparezca un PAN que
    # nunca existio. Exigir evidencia repetida — o un beacon, o un equipo con
    # OUI — es lo que separa un censo de una lista de ruido.
    MIN_FRAMES = 3
    weak = [k for k, r in nets.items()
            if not r["beacons"] and not r["devices"] and r.get("frames", 0) < MIN_FRAMES]
    for k in weak:
        unattributed += nets[k].get("frames", 0)
        del nets[k]

    out = []
    for row in nets.values():
        row["devices"] = sorted(row["devices"])
        row["device_count"] = len(row["devices"])
        row.setdefault("frames", 0)
        out.append(row)
    out.sort(key=lambda r: (-(r["beacons"] + r["device_count"] + r["frames"]), r["channel"] or 0))
    if with_unattributed:
        return out, unattributed
    return out


def describe(row: dict) -> str:
    """One honest line about a network."""
    bits: list[str] = []

    if row["vendors"]:
        bits.append(" + ".join(
            v + ("" if confirmed else " (?)") for v, confirmed in sorted(row["vendors"].items())
        ))

    if row["zigbee"]:
        bits.append(STACK_PROFILES.get(row["stack_profile"], f"profile {row['stack_profile']}"))
    elif row["zigbee"] is False:
        # Distinguish "definitely another stack" from "the beacon was too weak or
        # too short to tell". At -90 dBm a truncated frame looks identical to a
        # proprietary one, and calling that Crestron would be a guess dressed up
        # as a finding.
        if row["best_rssi"] <= -85 or row["payload_len"] < 15:
            bits.append("beacon without readable Zigbee payload — weak or truncated, "
                        "not identified")
        else:
            bits.append("802.15.4 but not Zigbee — another vendor's stack on the same "
                        "radio (Crestron infiNET EX behaves this way)")

    if row["device_count"]:
        bits.append(f"{row['device_count']} device(s) seen")
    elif row.get("frames"):
        # Sin direcciones largas no hay OUI, y sin OUI no hay marca. En una red
        # ya formada eso es lo normal, no una falla.
        bits.append(f"{row['frames']} trama(s), marca no visible — todo va con "
                    "direcciones cortas")
    if not row["from_beacon"] and not row["beacons"]:
        bits.append("sin beacon")

    if row["permit_join"]:
        bits.append("PERMIT-JOIN OPEN")
    return " · ".join(bits) or "unidentified"


def main() -> int:
    args = [pathlib.Path(a) for a in sys.argv[1:]]
    if not args:
        here = pathlib.Path(__file__).resolve().parent.parent
        args = [p for p in sorted((here / "captures").rglob("*.pcap"))
                if not p.name.endswith(".15p4.pcap")]
    if not args:
        print("\n  No captures to read. Run a scan first.\n")
        return 1

    rows = census(args)
    print()
    print(f"  802.15.4 network census — {len(args)} capture(s)")
    print()
    if not rows:
        print("  No networks identified.")
        print()
        print("  Not proof the air is empty: idle networks beacon rarely and a short")
        print("  dwell can miss them entirely. Sweep longer before concluding.")
        print()
        return 0

    print(f"  {'ch':<4} {'PAN':<8} {'RSSI':<6} {'bcn':<5} network")
    print(f"  {'----':<4} {'--------':<8} {'------':<6} {'-----':<5} -------")
    for r in rows:
        rssi = str(r["best_rssi"]) if r["best_rssi"] > -128 else "?"
        print(f"  {r['channel'] or '?':<4} {r['pan'] or '?':<8} {rssi:<6} "
              f"{r['beacons']:<5} {describe(r)}")
        if r["ext_pan"]:
            print(f"       ext PAN {r['ext_pan']}  (random on many coordinators — not a brand)")
        for mac in r["devices"][:4]:
            print(f"       device  {mac}")
    print()

    if any(r["permit_join"] for r in rows):
        print("  WARNING: a network beaconed with permit-join open. Anyone in range")
        print("  can add a device to it. Worth telling the customer.")
        print()

    print("  Reminder: this hears 802.15.4 only. Lutron Clear Connect Type X, Wi-Fi")
    print("  and Bluetooth share this band and stay invisible here — see docs/RF-BANDS.md")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
