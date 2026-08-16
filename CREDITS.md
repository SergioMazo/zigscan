# Credits

zigscan is a thin layer over other people's hardware and radio work. The
interesting parts — getting a CC1352P7 to hand you 802.15.4 frames over USB —
were solved upstream. This is worth stating plainly rather than in a footnote.

## Electronic Cats — CatSniffer and CatSniffer-Tools

<https://github.com/ElectronicCats/CatSniffer> ·
<https://github.com/ElectronicCats/CatSniffer-Tools>

The CatSniffer board (RP2040 + CC1352P7 + SX1262) and its toolchain are
Electronic Cats' work, licensed **GPL-3.0**. `setup.sh` fetches CatSniffer-Tools
at a pinned commit; it is not redistributed inside this repository, and its
copyright and licence stay with Electronic Cats.

Specifically, zigscan drives:

- **`pycatsniffer_bv3`** — the capture engine. Every pcap this tool analyses was
  produced by `cat_sniffer.py`.
- **`catnip_uploader`** — the only supported way to write firmware to the
  CC1352P7. Driving the raw bootloader by hand bricks the radio; this is not a
  theoretical warning.

Electronic Cats builds open hardware in Mexico. If this tool is useful to you,
buy the board from them: <https://electroniccats.com>

## Texas Instruments

The CC1352P7 and its **SmartRF sniffer firmware** are TI's. The firmware image
ships from Electronic Cats' releases under TI's own terms and is not included
here.

## Wireshark / tshark

Frame dissection for the deep-dive view. <https://www.wireshark.org>

## Origin

zigscan was extracted from a Control4 Zigbee protocol lab, where the console
was built to make a reverse-engineering bench legible to a technician. The
survey half turned out to be the part with a life of its own: the analysis is
generic 802.15.4, so it works on any Zigbee system regardless of brand.

## Licence

GPL-3.0, inherited from CatSniffer-Tools. See [LICENSE](LICENSE).
