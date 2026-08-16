# Choosing a radio for each technician

## The short answer

**Use another CatSniffer v3.x for each technician.** It is the only radio that
ZigScan currently supports end to end. Standardizing on one model also means
one firmware procedure, one manual, and one known set of failure modes.

The longer answer matters because ZigScan separates capture from analysis, and
that design leaves room for other radios.

## ZigScan has two halves, and only one depends on the radio

**Capture** communicates with the CatSniffer through Electronic Cats'
`pycatsniffer`. That path is specific to this hardware.

**Analysis**—network census, interference diagnosis, and the spectrum chart—does
not access the radio. It reads `.pcap` files and decodes 802.15.4, so this half
is hardware-independent.

This has been verified rather than assumed. A capture was converted to standard
Wireshark format (link type 195, without the TI-specific header), and the census
still found the network, both vendor identities, and the open permit-join state.
Only the channel and RSSI were lost because those values live in the TI header,
not in the standard frame format.

**Practical consequence:** any sniffer that produces an 802.15.4 `.pcap` can
feed the Analysis commands **today**, without code changes:

```bash
./zigscan census  capture-from-another-sniffer.pcap
./zigscan verdict capture-from-another-sniffer.pcap
```

Each additional radio would still need its own backend for **live capture**.
That requires code, not configuration.

## Radio options

| Radio | Approximate price | Live capture from ZigScan | Notes |
|---|---:|---|---|
| **CatSniffer v3.x** (Electronic Cats) | US$60–70 | **Yes, today** | CC1352P7 + RP2040 + SX1262. The SX1262 may support a future sub-GHz mode, subject to direct testing. |
| **nRF52840 Dongle** (Nordic) | US$10–20 | No — new backend required | Nordic provides *nRF Sniffer for 802.15.4* for Wireshark. Its standard PCAPs can already be analyzed with ZigScan. |
| **CC2652 USB** (Sonoff ZBDongle-**P**, zzh!, TubesZB) | US$20–35 | No — new backend required | TI sniffer firmware is available for this family. These adapters are common in the Zigbee ecosystem. Not tested with ZigScan live capture. |
| **TI LAUNCHXL-CC26X2R1 / CC1352P** | US$40–50 | No — new backend required | Official TI development boards using the same sniffer family. Useful as a reference against SmartRF Packet Sniffer 2. Not tested with ZigScan. |
| **CC2531** | ~US$10 | No | Obsolete. Its slow USB interface can lose frames under heavy traffic. Not recommended for new field work. |
| **Sonoff ZBDongle-E** (EFR32MG21) | ~US$25 | No | Silicon Labs hardware, not TI. Sniffing requires the Silicon Labs toolchain. It is commonly used as a coordinator, which is a different role. |

These entries describe technical paths, not verified compatibility. The tested
hardware matrix in [HARDWARE.md](HARDWARE.md) is the source of truth for direct
ZigScan validation.

## Recommendation by scenario

**A technician who only runs surveys** → CatSniffer v3.x. This is the validated
path available today.

**Several technicians on a limited budget** → use a CatSniffer for the person
running live ZigScan surveys. Other technicians can capture standard 802.15.4
PCAPs with their existing supported tools and send the files for ZigScan
Analysis. Validate this workflow with each radio before using it on customer
jobs.

**Future sub-GHz coverage** → the CatSniffer includes an SX1262, but ZigScan does
not currently provide a tested sub-GHz mode. Track that work separately and do
not claim support until it has been verified on physical hardware.

## Do not repurpose a coordinator

If an installation uses a CatSniffer as its coordinator, **do not flash it for
sniffing**. The sniffer firmware is a one-way door over serial: returning from
it requires SWD and a probe. Buy a second radio; it costs less than a recovery
visit.

## Firmware on a new unit

A new CatSniffer **does not arrive with the sniffer firmware installed**. The
unit used for this project was flashed in two stages on 2026-08-06, providing
direct evidence for the procedure. Assume that every new unit needs the same
process and verify it with `./zigscan identify` before leaving for a job. The
complete procedure is in section 3 of the [manual](MANUAL.md#3-firmware-a-new-radio-is-not-ready-out-of-the-box).
