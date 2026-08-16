# Contributing

Bug reports and field validation are welcome, especially for hardware revisions
not yet listed in the tested matrix.

Before opening an issue or pull request:

- reproduce on a temporary network when possible;
- do not upload customer or persistent-lab PCAPs;
- redact SSIDs, PAN IDs, addresses, serial numbers and site details;
- distinguish hardware directly tested from hardware inferred to be compatible;
- preserve ZigScan's passive operation: surveys and captures must never join,
  pair, inject or transmit into the observed network.

Functional changes should include a focused test and describe the hardware used
for validation. Changes that affect capture framing, channel selection or radio
control need verification on a CatSniffer before release.
