# Field Guide

For the technician arriving on site. Five minutes, not five pages.

## Before leaving the office

- Run `./zigscan identify`. If it cannot see the radio in the office, it will
  not see it at the customer's site either.
- Confirm that the 2.4 GHz antenna is attached to the SMA connector. Without
  the antenna, every channel looks clean and the report is misleading.
- Run `setup.sh` at least once before the visit. Reliable internet access cannot
  be assumed on site.

## On site

**1. Open the console.**

```bash
./zigscan survey
```

**2. Run the sweep.** Six seconds per channel takes about two minutes in total.
Place the laptop near the future coordinator location, not by the front door.
The relevant RF environment is where the devices will operate.

**3. Read the result.**

- **Recommended channel** — the cleanest option among 15, 20, 25 and 26. This
  is the operational answer you came for.
- **Busiest channel** — usually the system already installed at the site. If a
  customer's existing hub will remain, that channel is occupied.
- **No traffic on any channel** — suspect the antenna before trusting the result.

**4. If the visit is for a problem rather than a plan.** When the complaint is
"the lights respond slowly," the sweep shows whether the channel is congested.
If the channel is clean and the problem remains, the likely cause is the mesh,
routing, or power—not RF interference. The sweep has still done its job by
eliminating the most expensive cause to rule out manually.

## What the sweep does not answer

The radio listens to Zigbee, not Wi-Fi. A zero channel means *there is no Zigbee
traffic here*, not *there is no interference here*. A microwave or a saturated
access point can destroy a channel that looks empty in an 802.15.4 report. At a
Wi-Fi-dense site, ZigScan complements a spectrum survey; it does not replace it.

Zigbee can also be very quiet while idle. If you suspect a network is present
but the sweep misses it, ask someone to switch a light on and off while you scan
that channel, or increase the time per channel to 15 seconds.

## Save the job record

CLI captures are stored in `captures/` with timestamps. Keep them with the job
record. If a customer says six months later that the installation has "always
been slow," you will have the measurement from installation day.
