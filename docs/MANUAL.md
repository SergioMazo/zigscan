# ZigScan Manual

For the technician who will use it on site. If you only need the field summary,
see [FIELD-GUIDE.md](FIELD-GUIDE.md); it fits on one page.

---

## 1. What it does — and what it does not

ZigScan answers one question: **which Zigbee channel should this system use in
this building?** It answers a second question when there is already a problem:
**are the lights responding slowly because of interference or because of the
mesh?**

It answers by listening. **The radio never transmits**, so ZigScan can run next
to a live customer system without touching it. ZigScan does not join, pair,
inject or transmit into the Zigbee network. The CatSniffer operates as a passive
receiver during surveys and captures.

**What it cannot see.** The radio listens to 802.15.4, which covers Zigbee. It
does not see Wi-Fi directly (ZigScan measures that separately with the laptop's
Wi-Fi card), Bluetooth, Lutron Clear Connect Type X, or anything outside
2.4 GHz. A channel with zero frames means *there is no Zigbee traffic here*;
it never means *there is no interference here*. The complete limits are in
[RF-BANDS.md](RF-BANDS.md). Read it once before the first site visit.

---

## 2. What you need

| | |
|---|---|
| Radio | Electronic Cats CatSniffer v3.x |
| 2.4 GHz antenna | Attached to the SMA connector. Without it, every channel looks clean and the report is misleading. |
| Firmware | TI sniffer firmware on the CC1352P7 — see section 3. **A new radio is not ready out of the box.** |
| Laptop | macOS today. For Windows, see [HARDWARE-OPTIONS.md](HARDWARE-OPTIONS.md). |

---

## 3. Firmware: a new radio is not ready out of the box

A new CatSniffer **does not ship with the sniffer firmware installed**. It needs
two flashing stages because the board contains two chips:

1. **RP2040** (the USB interface) needs `SerialPassthroughwithboot`. This stage
   uses drag and drop: double-click the `reset1` button quickly, wait for a drive
   named `RPI-RP2`, copy the `.uf2` file to it, and let the board restart.
2. **CC1352P7** (the radio) needs `sniffer_fw`. This stage runs over serial with
   `catnip_uploader`.

**Verify instead of assuming:**

```bash
./zigscan identify
```

If it reports `TI sniffer firmware — answered the @S ping live`, the radio is
ready. If it reports `coordinator` or `unknown`, the sniffer firmware is missing.

### Three warnings that can prevent an expensive mistake

**Do not call `cc2538-bsl` manually.** The CC1352 bootloader on this board does
not open through a simple flag. The RP2040 sketch listens for a magic string
(`<boot>`) at 921600 baud and controls the pins itself. `catnip_uploader` performs
the complete sequence. Inventing a different handshake is how the radio can be
bricked; it already happened once during this project.

**Stage 1 must come first.** Any other RP2040 sketch ignores the magic string,
so the radio flashing process cannot find the bootloader.

**The sniffer firmware is a one-way door over serial.** Flashing *to* the
sniffer works. Flashing *from* the sniffer over serial does **not**:
`cc2538-bsl` never synchronizes because the TI build leaves the ROM in a state
that cannot exit through UART. Returning to coordinator firmware requires SWD
and a probe. That is why ZigScan never flashes firmware automatically, even
when it detects the wrong image: it reports the state and leaves the decision
to you.

If the radio is also the coordinator of an installation, **do not flash it**.
Buy a second unit.

---

## 4. Installation

### For technicians: the DMG

1. Open `zigscan.dmg` and drag **ZigScan** to Applications.
2. **On the first launch, right-click the app, select Open, and confirm.** A
   normal double-click may be blocked the first time because the current DMG is
   not notarized by Apple. This is required only once.
3. The app starts the local service and opens your default browser.

There is nothing else to install. The app does not require Python, Homebrew, or
administrator access. Once installed, it works without internet access. That
matters on job sites, where connectivity is unreliable and asking for the
customer's Wi-Fi password just to run a survey is poor practice.

**Your captures are stored in `~/Documents/zigscan/captures`**, outside the
application. They remain available if you update or delete the app, and you can
attach them to the job record directly from Finder.

To stop the service, quit the app with Cmd-Q like any other macOS application.

### For source-code users

```bash
git clone https://github.com/SergioMazo/zigscan.git
cd zigscan
./setup.sh
```

`setup.sh` creates the environment, downloads the Electronic Cats toolchain at
a pinned commit, and installs the required dependencies. It does not touch the
radio firmware. The terminal commands in section 5 are then available.

---

## 5. Usage

### The console

```bash
./zigscan survey
```

This opens `http://127.0.0.1:8477`. Everything runs locally; no data is uploaded.

In the upper-right corner, a green dot and the serial-port name confirm that the
radio is available. If the dot is red, the radio is missing. Check the cable and
make sure a virtual machine has not captured the USB device; Parallels can do
this automatically.

The **ES / EN** control changes the application language and remembers the
selection.

Every panel has a **`?`** explaining what it measures, what it **cannot** see,
and how to act on the result. If a number is unclear, start there.

### Field mode

The large number at the top is the operational answer: **the channel to use**.
The sentence below explains why.

- **2.4 GHz occupancy** — each bar is a channel; its height represents the
  frames received. Purple bands show the building's measured Wi-Fi. Dotted bars
  are **unmeasured** channels, which is not the same as clean channels.
- **Who is already on the air** — networks already operating at the site, with
  vendor evidence when it can be read.
- **Wi-Fi on site** — all three Wi-Fi bands. Only 2.4 GHz competes with Zigbee;
  5 and 6 GHz are included because the same technician often installs the Wi-Fi.
- **Diagnosis** — interference versus a mesh problem.
- **How to read signal** — what each dBm range means in practical distance.

### Analysis mode

Use Analysis when you need to look below the answer: capture one channel,
inspect decoded frames, or take the raw `.pcap` into Wireshark.

### From the terminal

```bash
./zigscan scan 6          # sweep all 16 channels, 6 s each (~2 min)
./zigscan census          # show who is already on the air
./zigscan verdict         # distinguish interference from a mesh problem
./zigscan wifi            # measure Wi-Fi across all bands
./zigscan capture 15 60   # record channel 15 for 60 seconds
./zigscan identify        # identify the radio and its firmware
```

---

## 6. Reading the results

### Recommended channel

The recommendation considers channels **15, 20, 25 and 26**, which fall in the
gaps around Wi-Fi channels 1, 6 and 11. Among those candidates, ZigScan first
prefers the channel with the least Wi-Fi overlap, then one without a known
network, and then the quietest remaining option.

ZigScan **never recommends a channel it did not measure**. If you see
"not swept," there is no survey data yet; it does not mean the channel is clean.

### Signal

| Reading | Meaning |
|---|---|
| −45 dBm | Inside this building, close to the measurement point |
| −62 dBm | Inside the building, at a normal working distance |
| −78 dBm | Far away, on another floor, or at a neighboring property; not reliable |
| −92 dBm | At the edge of audibility; almost certainly not part of this installation |

RSSI is especially useful for excluding unrelated networks. If a network
appears at −90 dBm, it is probably not the customer's problem.

### Diagnosis

| Result | What to do |
|---|---|
| **Interference** | Move the network to a clean channel. |
| **Not RF — the mesh** | Changing channels will not fix it. Check distance, repeaters, routing, and powered devices. |
| **Marginal** | It works without headroom. Fix it before more devices are added. |
| **RF is healthy** | The air is not the problem. Check the hub, integration, and automations. |
| **Not enough traffic** | Capture for longer or during the period when the customer reports the problem. |

The fourth result is as valuable as the others: **proving that RF is not the
problem** prevents an entire day from being spent chasing it.

### Open permit-join

If a network has this red label, it is accepting new devices from anyone within
range. Treat it as a security finding and inform the customer.

---

## 7. Troubleshooting

**The radio does not appear.** Make sure no virtual machine has claimed it.
Parallels can capture the device as soon as a VM starts, preventing macOS from
creating the serial port. `./zigscan identify` reports what it can see.

**The sweep reports zero on every channel.** Check these causes in order:

1. The 2.4 GHz antenna is not attached.
2. The network is idle. Quiet Zigbee traffic is normal. Ask someone to switch a
   light on and off during the sweep, or increase the time per channel to
   15 seconds.
3. The radio does not have the sniffer firmware (`./zigscan identify`).

**The census does not show a vendor.** This is expected on an established
network: normal traffic uses 16-bit short addresses, which do not carry a
manufacturer identifier. Vendor evidence is visible when a device joins. If
you need it, capture while a device is being paired.

**A network appears and disappears between sweeps.** This is normal when it is
near the edge of the signal range. Check its dBm value before reporting it.

---

## 8. Saving the job record

CLI captures are stored in `captures/` with timestamps. Keep them with the job
record. If a customer says six months later that the installation has "always
been slow," you will have the measurement from installation day.

Treat captures as sensitive data. A `.pcap` contains customer network traffic,
and a capture made during pairing can include a key exchange. Do not publish or
share captures outside the job without deliberate review and authorization.
