#!/usr/bin/env python3
"""What Wi-Fi is in the air here, measured with the laptop's own card.

Two jobs, one scan:

  1. Zigbee channel choice. Only 2.4 GHz matters — Zigbee lives nowhere else, so
     a 5 or 6 GHz access point cannot interfere with it no matter how loud it
     is. Drawing those bands over a Zigbee chart would be a lie, so this module
     computes the overlap for 2.4 GHz only.
  2. Wi-Fi channel choice, which is a different job the same technician has on
     the same visit. For that, every band counts, so all of them are reported.

Read-only and passive: macOS is asked what it already sees. Nothing is
transmitted, no interface is reconfigured, and no password is needed.

Limitation worth knowing before you trust a number: macOS reports signal
strength only for the network this Mac is *connected to*. Neighbouring networks
come back with channel and width but no RSSI, so occupancy here means "how many
access points sit on this channel", never "how loud they are".

Needs no sudo. `airport -s` was removed in macOS 14.4; this uses system_profiler,
which still works.
"""

from __future__ import annotations

import json
import re
import subprocess
import time

# Zigbee's occupied bandwidth is 2 MHz (O-QPSK), so ±1 MHz around the centre.
ZIGBEE_HALF_WIDTH = 1.0


def zigbee_centre(ch: int) -> int:
    """IEEE 802.15.4 2.4 GHz channel centre, MHz. Channels 11-26."""
    return 2405 + 5 * (ch - 11)


def wifi_centre(ch: int, band: str) -> int | None:
    """Wi-Fi channel centre in MHz, per band."""
    if band == "2.4":
        if ch == 14:            # Japan only, and 12 MHz above 13
            return 2484
        if 1 <= ch <= 13:
            return 2407 + 5 * ch
        return None
    if band == "5":
        return 5000 + 5 * ch
    if band == "6":             # Wi-Fi 6E channel numbering
        return 5950 + 5 * ch
    return None


def _parse_channel(text: str) -> tuple[int | None, str, int]:
    """'40 (5GHz, 160MHz)' -> (40, '5', 160).

    macOS writes the 2.4 GHz band as '2GHz'; everyone else calls it 2.4, so it is
    normalised here rather than leaking the platform's spelling into the UI.
    """
    m = re.match(r"\s*(\d+)", text or "")
    ch = int(m.group(1)) if m else None

    band = ""
    if "2GHz" in text or "2.4GHz" in text:
        band = "2.4"
    elif "5GHz" in text:
        band = "5"
    elif "6GHz" in text:
        band = "6"

    m = re.search(r"(\d+)MHz", text or "")
    width = int(m.group(1)) if m else 20
    return ch, band, width


def _parse_rssi(text: str) -> int | None:
    """'-59 dBm / -94 dBm' -> -59."""
    m = re.match(r"\s*(-?\d+)\s*dBm", text or "")
    return int(m.group(1)) if m else None


def _clean(name: str) -> str:
    return (name or "").strip() or "(hidden)"


def scan(timeout: int = 60) -> dict:
    """Ask macOS what it sees. Slow (seconds) — cache the result."""
    out: dict = {
        "ok": False, "note": "", "note_code": "", "scanned_at": time.time(),
        "interface": None, "networks": [], "bands": {}, "zigbee_overlap": {},
    }

    try:
        p = subprocess.run(
            ["system_profiler", "-json", "SPAirPortDataType"],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        out["note_code"] = "scan_failed"
        out["note"] = f"Wi-Fi scan failed: {type(exc).__name__}"
        return out

    if p.returncode != 0:
        out["note_code"] = "profiler_error"
        out["note"] = "system_profiler returned an error."
        return out

    try:
        data = json.loads(p.stdout)
    except ValueError:
        out["note_code"] = "parse_failed"
        out["note"] = "Could not parse the Wi-Fi report."
        return out

    ifaces = []
    for section in data.get("SPAirPortDataType", []):
        ifaces.extend(section.get("spairport_airport_interfaces", []) or [])

    nets: list[dict] = []
    for iface in ifaces:
        name = iface.get("_name", "")
        # awdl0 / p2p0 are AirDrop and peer-to-peer virtual interfaces. They
        # report a "network" that is not an access point and would inflate the
        # counts.
        if not name.startswith("en"):
            continue
        if out["interface"] is None:
            out["interface"] = name

        cur = iface.get("spairport_current_network_information") or {}
        if cur:
            ch, band, width = _parse_channel(cur.get("spairport_network_channel", ""))
            if ch and band:
                nets.append({
                    "ssid": _clean(cur.get("_name")),
                    "channel": ch, "band": band, "width": width,
                    "rssi": _parse_rssi(cur.get("spairport_signal_noise", "")),
                    "phy": cur.get("spairport_network_phymode", ""),
                    "current": True,
                })

        for other in iface.get("spairport_airport_other_local_wireless_networks", []) or []:
            ch, band, width = _parse_channel(other.get("spairport_network_channel", ""))
            if not ch or not band:
                continue
            nets.append({
                "ssid": _clean(other.get("_name")),
                "channel": ch, "band": band, "width": width,
                "rssi": None,          # macOS does not report it for neighbours
                "phy": other.get("spairport_network_phymode", ""),
                "current": False,
            })

    if not nets:
        out["note_code"] = "no_networks"
        out["note"] = ("No Wi-Fi networks reported. Is Wi-Fi switched on? A Mac on "
                       "Ethernet with Wi-Fi off scans nothing.")
        return out

    # Span each network occupies, so overlap is computed from frequency rather
    # than from channel numbers — 2.4 GHz channels overlap each other, which is
    # exactly the thing channel-number arithmetic gets wrong.
    for n in nets:
        centre = wifi_centre(n["channel"], n["band"])
        n["centre"] = centre
        if centre:
            n["lo"] = centre - n["width"] / 2
            n["hi"] = centre + n["width"] / 2

    bands: dict[str, dict] = {}
    for n in nets:
        b = bands.setdefault(n["band"], {"aps": 0, "channels": {}})
        b["aps"] += 1
        b["channels"][n["channel"]] = b["channels"].get(n["channel"], 0) + 1

    overlap: dict[int, dict] = {}
    for zb in range(11, 27):
        c = zigbee_centre(zb)
        lo, hi = c - ZIGBEE_HALF_WIDTH, c + ZIGBEE_HALF_WIDTH
        hits = [n for n in nets
                if n["band"] == "2.4" and n.get("lo") is not None
                and n["lo"] < hi and n["hi"] > lo]
        overlap[zb] = {
            "aps": len(hits),
            "ssids": sorted({n["ssid"] for n in hits})[:6],
        }

    out.update({"ok": True, "networks": nets, "bands": bands, "zigbee_overlap": overlap})
    return out


def recommend_wifi_24(result: dict) -> dict:
    """Least crowded of the three non-overlapping 2.4 GHz channels.

    1 / 6 / 11 are the only 2.4 GHz channels that do not overlap each other, so
    a recommendation outside that set would create the very interference it is
    trying to avoid — even when the channel looks empty.
    """
    if not result.get("ok"):
        return {}
    counts = {ch: 0 for ch in (1, 6, 11)}
    for n in result.get("networks", []):
        if n["band"] != "2.4" or n.get("lo") is None:
            continue
        for ch in counts:
            c = wifi_centre(ch, "2.4")
            if n["lo"] < c + 10 and n["hi"] > c - 10:
                counts[ch] += 1
    pick = min(counts, key=lambda c: counts[c])
    return {"channel": pick, "aps": counts[pick], "counts": counts}


if __name__ == "__main__":
    import sys

    r = scan()
    if not r["ok"]:
        print(r["note"] or "scan failed")
        sys.exit(1)

    print(f"\n  Interface {r['interface']} — {len(r['networks'])} networks\n")
    for band in ("2.4", "5", "6"):
        b = r["bands"].get(band)
        if not b:
            continue
        chans = ", ".join(f"ch{c}×{n}" for c, n in sorted(b["channels"].items()))
        print(f"  {band:>3} GHz  {b['aps']:>3} AP  {chans}")

    rec = recommend_wifi_24(r)
    if rec:
        print(f"\n  Wi-Fi 2.4 GHz: use channel {rec['channel']} ({rec['aps']} AP) "
              f"— counts {rec['counts']}")

    busy = {ch: v for ch, v in r["zigbee_overlap"].items() if v["aps"]}
    print(f"\n  Zigbee channels sitting under Wi-Fi: "
          f"{', '.join(str(c) for c in sorted(busy)) or 'none'}\n")
