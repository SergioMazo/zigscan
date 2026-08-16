# ZigScan 0.3.0

The first public release of ZigScan, a Zigbee RF diagnostic and site-survey tool
for AV integrators.

## Highlights

- **Field:** sweep Zigbee channels 11-26, compare them with measured Wi-Fi
  occupancy, identify detected PANs and vendor evidence, evaluate RSSI and
  permit-join, recommend a channel, and distinguish interference from mesh
  problems through retransmission analysis.
- **Analysis:** run targeted captures, inspect PCAP frames and individual RSSI,
  see MAC commands, ACKs and source/destination addressing, and continue the
  investigation in Wireshark.
- **Passive by design:** the CatSniffer receives only. ZigScan does not join,
  pair, inject or transmit into the Zigbee network.

## Download

The release asset is `zigscan.dmg` for macOS. It is currently unsigned and not
notarized, so the first launch requires right-clicking the app and choosing
**Open**. See `docs/MANUAL.md` section 4.

Source users can clone the repository and run `./setup.sh` followed by
`./zigscan survey`.

## Directly verified

- Electronic Cats CatSniffer v3.1 with TI Sniffer 1.10.0
- Control4 SR260 observed passively on a live Zigbee network
- Sonoff ZBDongle-E observed passively on a live Zigbee network

Other models and hardware revisions need community testing. Windows, Apple
Developer signing/notarization, and unverified OUI mappings remain outside this
release's verified scope.
