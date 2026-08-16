# Changelog

## 0.3.1 — 2026-08-15

**Fixed**
- All public repository documentation is now consistently written in English.
  The ES/EN selector remains available inside the application.
- The synthetic demo capture now includes an extended address built from
  Control4's public `00:0f:ff` OUI and deterministic fictional device bytes.
  Census can demonstrate vendor detection without distributing a real device
  identity, network key, or over-the-air capture.
- The source installation command in the manual now points to
  `https://github.com/SergioMazo/zigscan.git`.

## 0.3.0 — 2026-08-15

A macOS app a technician can install, and the capture rework that made it
possible.

**Added**
- A dedicated ZigScan application icon, used by the macOS bundle and README.
- `zigscan.app` and `zigscan.dmg`, built by `./build-macos.sh`. The app starts
  the console and opens the technician's own default browser. No Python, no
  Homebrew, no admin rights.
- `tools/paths.py` separates read-only bundled resources from writable data.
  Captures go to `~/Documents/zigscan` — a folder the technician can actually
  find in Finder, which survives replacing the app, and which is writable where
  the bundle is not.
- The build script strips extended attributes before signing. iCloud and Finder
  attach them, and `codesign` refuses a bundle that carries them — it breaks
  even the ad-hoc signature PyInstaller applies to its own output.
- Signing and notarisation are wired but optional: set `ZIGSCAN_SIGN_ID` and
  `ZIGSCAN_NOTARY_PROFILE` and the right-click-to-open step disappears.

**Fixed**
- The frozen worker's output reached the console in bursts, so the sweep
  progress bar sat at zero and then jumped to done. A windowed app has no tty,
  so Python block-buffers; stdout is line-buffered explicitly now.
- Switching the Analysis view from ES to EN now also updates empty and error
  states such as `No jobs yet.`; backend error and Wi-Fi status codes are
  rendered in the selected language, and capture workers receive that language
  for their live console output.
- Per-channel files from different sweeps no longer appear as identical
  `ch15.pcap` rows. Their UI labels include the sweep time, while their paths
  and on-disk storage remain unchanged.

**Changed**
- `tools/capture.py` replaces `scan_channels.sh` and `sniff_zigbee.sh`. Those
  drove pycatsniffer by launching `.venv/bin/python cat_sniffer.py` and piping
  commands into its REPL — fine on a bench, impossible inside a bundle, where
  there is no virtualenv, no absolute paths and no second interpreter to launch.
  Electronic Cats' `SnifferCollector` is now driven directly, in process.
  This also removes the last reason the project needed two virtualenvs, and it
  is the same change that makes a Windows build possible later.
- The console starts jobs with `sys.executable` instead of `/bin/bash`.
- Public sample PCAPs must come from a temporary, disposable demo PAN. The real
  lab join capture was removed from the release set rather than anonymised or
  redistributed; a reproducible synthetic join fixture now exercises Analysis
  and census without carrying captured RF traffic or real identifiers.

**Fixed**
- Capture files are written where we ask. Upstream's `get_filename()` mixes a
  timestamp with a fresh `uuid4()` on every call, and `run()` calls it three
  times, so not even upstream can name the file it just opened — which is why
  the old scripts had to `find` the result afterwards.
- pycatsniffer's own output no longer buries the channel table. Its `LOG_*`
  helpers are bare prints with ANSI colour and a malformed frame from a
  neighbour's network produces a multi-line dissector warning per packet. Set
  `ZIGSCAN_VERBOSE=1` to see them again when debugging.

**Verified on hardware** (CatSniffer v3.1, TI sniffer 1.10.0, live Zigbee network
on channel 15): single capture 29 frames in 12 s, linktype 147, census resolved
PAN 0xfebd; sweep across channels 15/20/25 recorded activity only on 15 and wrote
its manifest.

## 0.2.1 — unreleased

**Added**
- ES / EN toggle in the header, remembered per browser. Every user-facing
  sentence lives in the page; the backend returns numbers and a level code and
  writes no prose, so adding a language never touches Python. The diagnosis was
  the last holdout — it arrived pre-written in English from `verdict.py` and
  stayed English with the page in Spanish.
  IEEE 802.15.4 frame and command names (Beacon, Data, ACK, Data Request) are
  deliberately left untranslated: they are the identifiers used in the spec, in
  Wireshark and in every vendor document, and translating them would break the
  one thing a technician cross-references.
- Progress bar while a sweep runs — channel N of 16 and elapsed time. Two
  minutes of silence made technicians press the button twice.
- A `?` on every panel with a field explanation of what it measures, what it
  cannot see, and what to do about it.
- Signal shown as a coloured bar with a plain-language label, plus a legend
  panel. −57 dBm means nothing to a technician; "inside this building" does.
- Aurora mark links to auroraproject.ai, and a footer signature.

**Fixed**
- The captures list read `c.rel` / `c.size`, which the API never returned — it
  serves `path` and `bytes`. Clicking a capture asked for an empty path and the
  generic catch reported "error reading capture". Errors now name the path, the
  HTTP status and the server's message.
- The chart mixed the current sweep with every capture ever taken, so a fresh
  site showed the previous job's traffic. With a sweep on disk the bars are the
  sweep; history stays in the analysis tab.
- The recommendation ignored the census. A 6-second dwell hears nothing on an
  idle network, so the tool would happily recommend the channel the customer's
  existing coordinator is already on. Channels with a known network are now
  penalised, and the answer says so.
- The census invented networks from single frames at −90 dBm. A PAN now needs
  three frames, a beacon, or a device with an OUI before it is reported.
- The census ignored the radio's own CRC verdict (RPI header byte 15, bit 7).
- The verdict measured every channel against the span between the first and
  last capture on disk — 3.2 days in one case. Spans are per file now.

**Changed**
- The census reads ordinary traffic, not just beacons and long addresses. A
  settled network uses 16-bit addresses and sends no beacons, so it was
  invisible; its PAN ID rides in every frame and is enough to detect it. Brands
  still need a join to be visible, and the UI says that rather than implying
  the network has none.

## 0.2.0 — unreleased

Renamed from `channelcat`. Three features that answer questions a spectrum
analyser cannot, and a UI rebuilt in Aurora's identity.

**Added**
- **Measured Wi-Fi** (`tools/wifi.py`). The 1 / 6 / 11 bands drawn on the chart
  were a textbook diagram; now they are this site's actual access points, read
  from the laptop's own card with no sudo and no password. All three bands are
  reported — 5 and 6 GHz cannot touch Zigbee, but the technician installing the
  Wi-Fi wants them on the same visit. Overlap is computed from frequency spans,
  not channel numbers: a single 40 MHz access point covers eight Zigbee
  channels, which channel arithmetic misses entirely.
- **Network census** (`tools/census.py`). Who is already on the air: PAN IDs,
  brands, permit-join state, Zigbee versus somebody else's stack. Brands come
  from the OUI of device addresses, never from the extended PAN ID — many
  coordinators generate that at random, so reading a vendor out of it produces
  confident nonsense.
- **Verdict** (`tools/verdict.py`). Interference or the mesh? Retransmission
  rate crossed with how busy the channel is. Proving RF is *not* the problem is
  the answer that saves the second visit.
- `docs/RF-BANDS.md` — what this tool sees per brand, and the three blind spots.
  Lutron Clear Connect Type X is 2.4 GHz with a proprietary PHY: it occupies the
  air and stays invisible here. That belongs in writing, not in folklore.
- The sweep now records **every channel it listened to**, including the empty
  ones, and the console refuses to recommend a channel it never measured.

**Changed**
- The UI moved out of a Python string into `tools/page.html` and was rebuilt on
  auroraproject.ai's design language. Two modes: **Field** for the technician
  who wants a channel number, **Analysis** for frames and captures.

**Fixed**
- CSS class collision: the top bar and the chart bars both used `.bar`, so the
  header rendered at 62% width with a stray background.
- The verdict timed every channel against the whole sweep's duration instead of
  its own, which turned a busy channel into a quiet one.

## 0.1.0 — unreleased

First extraction from the Control4 Zigbee lab console it grew out of.

**Added**
- `./zigscan` — single entry point: `survey`, `scan`, `identify`, `capture`,
  `report`, `convert`.
- Channel recommendation in `scan`: the quietest of Zigbee 15 / 20 / 25 / 26,
  the channels that fall between Wi-Fi 1 / 6 / 11. Previously the sweep only
  reported the *busiest* channel, which is the answer to a different question.
- `setup.sh` — one venv, and the Electronic Cats toolchain fetched at a pinned
  commit.
- Bilingual README, `docs/HARDWARE.md`, `docs/FIELD-GUIDE.md`.
- Two sample captures so the console renders before anyone owns a board.

**Fixed**
- The port probe no longer opens `/dev/cu.usbserial*`. Only the CatSniffer's
  `cu.usbmodem*` is ever selected. `--probe` *writes* to the port it picks, and
  on a bench with a second radio that meant writing Z-Stack bytes into a live
  Zigbee coordinator's serial stream.

**Removed**
- Everything specific to the originating lab: Home Assistant probes, zigpy quirk
  validation, the Control4 test suite, and the audit report that reported on
  them. What is left is generic 802.15.4.

**Known limits**
- macOS only — serial detection uses `/dev/cu.usbmodem*`.
- The Wi-Fi bands on the chart are the textbook 1 / 6 / 11 positions, drawn as a
  reference. They are not measured.
- Firmware switching is CLI-only, deliberately. It is not a thing to do on site.
