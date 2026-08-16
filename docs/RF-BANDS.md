# What ZigScan can see — and what it cannot

The rule in one sentence: **ZigScan listens to 802.15.4 at 2.4 GHz.** Nothing
else is received by the Zigbee capture path.

That covers Zigbee, excludes entire frequency bands, and—most importantly—also
excludes systems that **use 2.4 GHz** but speak a different radio protocol. A
channel that looks empty in ZigScan can still contain other RF energy. Understand
this boundary before presenting a channel recommendation to a customer.

## By system or vendor

| System | Band | Can ZigScan see it? |
|---|---|---|
| **Control4** | Zigbee, 2.4 GHz | **Yes, when 802.15.4 frames are received.** Beacons, device addresses, and public OUI evidence are decoded. Observed on real hardware. |
| **SONOFF / ITead** | Zigbee, 2.4 GHz | **Yes, when 802.15.4 frames are received.** Observed on real hardware. |
| **Philips Hue, Aqara, SmartThings** | Zigbee, 2.4 GHz | Public OUIs are present in the lookup table, but direct field confirmation is still required. |
| **Crestron infiNET EX** | 2.4 GHz over 802.15.4 | **Potentially partial.** It shares the 802.15.4 PHY and MAC, so compatible received frames may occupy the channel count, but a non-Zigbee payload will not be identified as a Zigbee network. Not verified against physical hardware. |
| **Lutron RadioRA 2, QS, Caséta** (Clear Connect Type A) | ~434 MHz | **No.** Different frequency band. It does not compete with Zigbee and cannot appear in a 2.4 GHz Zigbee capture. |
| **Lutron RadioRA 3, HomeWorks QSX** (Clear Connect Type X) | **2.4 GHz** | **No, and this is an important blind spot.** It occupies the same RF band but uses a proprietary PHY, so it does not produce 802.15.4 frames for ZigScan to count. Verify this boundary independently before relying on it in the field. |
| **Vantage RadioLink** | Sub-GHz | **No.** Different frequency band. |
| **Savant** | Depends on product line; some products use Zigbee | Depends on the specific hardware. Not verified. |

Rows marked as unverified come from publicly available technical information,
not direct measurements on this bench. Confirm them before using them in a
customer-facing conclusion. When direct evidence becomes available, update this
table and `OUI_VENDORS` in `tools/census.py` with the exact tested hardware and
firmware revision.

## Three blind spots

**Wi-Fi.** Wi-Fi does not generate 802.15.4 frames, so the Zigbee frame counter
cannot see it. ZigScan measures Wi-Fi separately with the laptop's Wi-Fi card
and overlays the observed channels on the spectrum chart. This is the one blind
spot the current tool already addresses directly.

**Other PHYs at 2.4 GHz.** Clear Connect Type X, Bluetooth, proprietary 2.4 GHz
systems, video senders, and microwave ovens can occupy the band without
producing an 802.15.4 frame. Zero received frames means *no 802.15.4 traffic was
heard here*; it never means *there is no interference here*.

**Quiet Zigbee networks.** An idle Zigbee network may transmit very little.
Routers send link-status traffic approximately every 15 seconds, and beacons
normally appear in response to a beacon request. A six-second sweep can pass
over a real network without hearing it. When the result matters, listen longer
or ask someone to operate a light while you measure.

## Possible future work

Two paths are technically interesting with the existing hardware, but neither
is a current compatibility claim:

**Energy detection.** The CC1352P7 can measure channel power regardless of the
protocol producing it. An energy sweep could distinguish "no Zigbee frames"
from "no RF energy," but ZigScan has not yet validated whether the current
`pycatsniffer` path exposes the required function.

**Sub-GHz.** The CatSniffer v3.x includes an SX1262 alongside the CC1352P7. The
chip covers 433/868/915 MHz, but ZigScan does not currently implement or claim a
tested sub-GHz survey mode. Any future mode must be verified on physical
hardware before the documentation lists supported systems.
