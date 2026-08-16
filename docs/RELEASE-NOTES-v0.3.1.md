# ZigScan 0.3.1

This patch release makes the public documentation consistently English and
improves the offline demonstration included with the application.

## Changes

- The manual, field guide, RF-band limits, and hardware-options guide are now
  written in English, matching the main repository and release pages.
- The manual's source installation command uses the canonical repository URL:
  `https://github.com/SergioMazo/zigscan.git`.
- The deterministic synthetic PCAP now exercises vendor detection with an
  extended address using Control4's public `00:0f:ff` OUI.
- The five device-specific bytes after the OUI are generated from the fixed demo
  seed. The sample contains no identity, key, or traffic from real hardware.

## Passive operation

**The radio never transmits.** ZigScan does not join, pair, inject or transmit
into the Zigbee network. The CatSniffer operates as a passive receiver during
surveys and captures.

## macOS download

The DMG is ad-hoc signed but not Apple-notarized. On first launch, right-click
ZigScan, choose **Open**, and confirm. No Python or Homebrew installation is
required.
