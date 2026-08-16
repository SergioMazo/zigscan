#!/usr/bin/env python3
"""Is it interference, or is it the mesh?

The most common Zigbee service call is "the lights respond slowly", and the
expensive part of answering it is deciding whether to blame the air or the
network. Both look identical from the customer's side, and guessing wrong costs
a second visit.

The capture already contains the answer. 802.15.4 retransmits a frame using the
*same* sequence number, so counting repeats tells you how hard the radios are
working to be heard. Cross that with how busy the channel is:

    retries HIGH + channel BUSY   -> interference. Move channel.
    retries HIGH + channel QUIET  -> not RF. Routing, repeater placement or
                                     power. Moving channel will not help.
    retries LOW                   -> the air is fine. Look elsewhere entirely.

That last line matters as much as the others: proving RF is *not* the problem is
what stops a technician spending a day chasing it.

Run:  ./zigscan verdict [capture.pcap ...]
"""

from __future__ import annotations

import pathlib
import struct
import sys

RPI_HEADER_LEN = 20

# Above this share of retransmitted data frames, the radios are struggling. Real
# Zigbee networks retry a little all the time; a tenth of frames is where it
# stops being normal and starts being felt as latency.
RETRY_WARN = 0.10
RETRY_BAD = 0.25

# Frames heard per second on the channel, from anyone, that count as "busy".
BUSY_FPS = 5.0


def analyse(paths: list[pathlib.Path]) -> dict:
    """Retry rate and traffic level, per channel."""
    per: dict[int, dict] = {}

    for path in paths:
        data = path.read_bytes()
        if len(data) < 24:
            continue
        magic, *_rest, link = struct.unpack("<LHHIILL", data[:24])
        if magic != 0xA1B2C3D4:
            continue

        off = 24
        while off + 16 <= len(data):
            ts, us, caplen, _orig = struct.unpack("<llll", data[off : off + 16])
            rec = data[off + 16 : off + 16 + caplen]
            off += 16 + caplen
            if caplen < 0:
                break

            ch = None
            if link == 147:
                if len(rec) < RPI_HEADER_LEN:
                    continue
                ch = struct.unpack("<H", rec[12:14])[0]
                frame = rec[RPI_HEADER_LEN : RPI_HEADER_LEN + rec[19]]
            else:
                frame = rec
            if len(frame) < 3 or ch is None:
                continue

            t = ts + us / 1e6
            # Timed per channel, not per file. A sweep writes several channels
            # into one run, and charging every channel the whole sweep's duration
            # would divide a busy channel's frames by the time spent on all the
            # others — turning a loud channel into a quiet one.
            e = per.setdefault(ch, {
                "frames": 0, "data": 0, "acks": 0, "retries": 0,
                "seen": {}, "span": 0.0, "first": None, "last": None,
            })
            # first/last se reinician por archivo: dos capturas tomadas con dias
            # de diferencia no forman un lapso continuo, y medir frames/segundo
            # contra el hueco entre ellas convierte un canal saturado en uno
            # tranquilo.
            e["first"] = t if e["first"] is None else min(e["first"], t)
            e["last"] = t if e["last"] is None else max(e["last"], t)
            e["frames"] += 1

            fcf = struct.unpack("<H", frame[:2])[0]
            ftype = fcf & 0x7
            seq = frame[2]

            if ftype == 2:                      # acknowledgement
                e["acks"] += 1
                continue
            if ftype not in (1, 3):             # data / MAC command
                continue

            e["data"] += 1
            # A retransmission reuses the sequence number within a short window.
            # Sequence numbers wrap at 256, so an unbounded memory would call a
            # legitimate wrap a retry; the window keeps that honest.
            key = (seq, frame[3:9])
            prev = e["seen"].get(key)
            if prev is not None and (t - prev) < 2.0:
                e["retries"] += 1
            e["seen"][key] = t

        # Cerrar el lapso de este archivo antes de pasar al siguiente.
        for e in per.values():
            if e["first"] is not None:
                e["span"] += e["last"] - e["first"]
                e["first"] = e["last"] = None
            e["seen"].clear()

    out = {}
    for ch, e in per.items():
        span = e["span"] or 1.0
        out[ch] = {
            "frames": e["frames"],
            "data": e["data"],
            "acks": e["acks"],
            "retries": e["retries"],
            "retry_rate": (e["retries"] / e["data"]) if e["data"] else 0.0,
            "fps": e["frames"] / span,
            "span": round(span, 1),
        }
    return out


def verdict_for(stats: dict, wifi_aps: int = 0) -> dict:
    """Turn one channel's numbers into something a technician can act on."""
    rate = stats["retry_rate"]
    busy = stats["fps"] >= BUSY_FPS or wifi_aps > 0

    if stats["data"] < 20:
        return {
            "level": "unknown",
            "headline": "Not enough traffic to judge",
            "detail": ("Fewer than 20 data frames were captured, which is too few to "
                       "measure a retry rate. Capture for longer, or during the hours "
                       "the customer complains about."),
        }

    if rate >= RETRY_BAD:
        if busy:
            return {
                "level": "interference",
                "headline": "Interference — move the network to a clear channel",
                "detail": (f"{rate:.0%} of data frames are retransmissions and the "
                           f"channel is busy ({stats['fps']:.1f} frames/s"
                           + (f", {wifi_aps} Wi-Fi AP overlapping" if wifi_aps else "")
                           + "). The radios are fighting for air."),
            }
        return {
            "level": "mesh",
            "headline": "Not RF — this is the mesh, not the channel",
            "detail": (f"{rate:.0%} of data frames are retransmissions, but the "
                       f"channel is quiet ({stats['fps']:.1f} frames/s). Changing "
                       "channel will not fix this. Look at distance, repeater "
                       "placement, routing and mains-powered device coverage."),
        }

    if rate >= RETRY_WARN:
        return {
            "level": "watch",
            "headline": "Marginal — working, but working hard",
            "detail": (f"{rate:.0%} of data frames are retransmissions. Not broken, "
                       "but there is no headroom. Worth fixing before the customer "
                       "adds more devices."),
        }

    return {
        "level": "ok",
        "headline": "RF is healthy — look elsewhere",
        "detail": (f"Only {rate:.0%} of data frames are retransmissions. Whatever "
                   "the complaint is, the air is not causing it. Check the hub, the "
                   "integration, the automations or the devices themselves."),
    }


def main() -> int:
    args = [pathlib.Path(a) for a in sys.argv[1:]]
    if not args:
        here = pathlib.Path(__file__).resolve().parent.parent
        args = [p for p in sorted((here / "captures").rglob("*.pcap"))
                if not p.name.endswith(".15p4.pcap")]
    if not args:
        print("\n  No captures to read. Capture a channel first.\n")
        return 1

    per = analyse(args)
    if not per:
        print("\n  Nothing readable in those captures.\n")
        return 1

    print()
    for ch in sorted(per):
        s = per[ch]
        v = verdict_for(s)
        print(f"  Channel {ch} — {s['frames']} frames in {s['span']}s "
              f"({s['data']} data, {s['acks']} ack, {s['retries']} retries)")
        print(f"    {v['headline']}")
        print(f"    {v['detail']}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
