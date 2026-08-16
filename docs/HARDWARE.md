# Hardware notes

## Tested hardware matrix

Only the combinations below have direct evidence. Other models and revisions
are not claimed compatible; community testing is welcome.

| Hardware | Firmware / role | Evidence |
|---|---|---|
| Electronic Cats CatSniffer v3.1 | TI Sniffer 1.10.0 | Tested: identification, targeted capture and complete 16-channel sweep. |
| Control4 SR260 | Device on a live Zigbee network | Observed passively in received traffic. ZigScan did not join or transmit. |
| Sonoff ZBDongle-E | Device on a live Zigbee network | Observed passively in received traffic. ZigScan did not join or transmit. |
| Other models or hardware revisions | Not verified | Community testing wanted; no compatibility claim yet. |

**The radio never transmits.** ZigScan does not join, pair, inject or transmit
into the Zigbee network. The CatSniffer operates as a passive receiver during
surveys and captures.

## The two firmware roles

The CC1352P7 runs one firmware at a time, and the two you care about do opposite
jobs:

| Role | Firmware | What it can do |
|---|---|---|
| **Sniffer** | TI SmartRF sniffer | Listens on one channel, receives everything, **transmits nothing**. This is what a survey needs. |
| **Coordinator** | Z-Stack ZNP | Forms and runs a Zigbee network, pairs devices, sends commands. Cannot capture other networks. |

Switching roles is a reflash, not a setting. `./zigscan identify` reports
which one is loaded.

For a site survey you want **sniffer**. It is also the safe choice: a passive
receiver cannot join or disturb the customer's system, so you can measure a live
installation without touching it.

## Flashing

Use Electronic Cats' `catnip_uploader`, which `setup.sh` installs:

```bash
cd tools/catsniffer-tools/catnip_uploader
../../../.venv/bin/python catnip_uploader.py load <firmware> <port>
```

**Do not drive the CC1352P7 bootloader by hand.** The serial bootloader needs a
specific entry sequence, and a hand-rolled handshake with a raw `cc2538-bsl`
invocation leaves the radio unresponsive — recovering it needs SWD and a probe.
This is written down because it has already happened once. `catnip_uploader` is
the supported path; there is no reason to take another one.

Firmware images come from Electronic Cats' releases, not from this repository.

## The antenna trap

The CatSniffer's SMA port needs a **2.4 GHz** antenna. With no antenna, or with
a sub-GHz one fitted, a sweep returns an almost-empty spectrum — which looks
exactly like a clean site. Every "there's no Zigbee here" result deserves a
glance at the connector before it becomes a recommendation.

## Serial port detection

The board's RP2040 is a native-USB CDC device, so macOS names it
`/dev/cu.usbmodem*`. That is the only pattern this tool will open.

`/dev/cu.usbserial*` ports are USB-UART bridges — FTDI, CP210x, CH34x. On a
bench with more than one radio, that is somebody else's coordinator. The
identify probe **writes** to the port it selects, so it lists those ports and
leaves them alone; probing a live coordinator injects bytes into its serial
stream and can knock a working system offline. Pass `--port` explicitly if you
genuinely need to interrogate one, and only when you know nothing else has it
open.

## Virtualisation steals the board

If you run Parallels, VMware or similar, the VM can claim the CatSniffer
exclusively the moment it starts. macOS then creates **no** `/dev/cu.*` node at
all and every tool here fails with a confusing serial error that looks like dead
hardware.

`./zigscan identify` detects this and names the owner. The fix is to release
the device in the VM's USB menu, not to re-plug the board.
