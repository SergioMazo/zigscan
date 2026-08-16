#!/usr/bin/env bash
#
# One-time setup. Creates the venv and fetches the Electronic Cats toolchain
# that actually drives the radio.
#
# Run once at the office, with internet. After this the tool works offline,
# which is the point — job sites rarely have usable Wi-Fi, and asking for the
# customer's password to run a survey is a bad look.
#
# Usage:  ./setup.sh

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENDOR="$HERE/tools/catsniffer-tools"

# Pinned, not floating. The capture path is sensitive to how cat_sniffer.py
# frames its output, and an upstream change would silently alter the pcaps this
# tool parses. Bump it deliberately, with hardware in hand.
UPSTREAM="https://github.com/ElectronicCats/CatSniffer-Tools.git"
PIN="69f61a4"

say() { printf '\n  %s\n' "$*"; }
die() { printf '\nERROR: %s\n\n' "$*" >&2; exit 1; }

command -v python3 >/dev/null 2>&1 || die "python3 not found."
command -v git     >/dev/null 2>&1 || die "git not found. Install the Xcode command line tools: xcode-select --install"

# ---------------------------------------------------------------------------
# 1. Electronic Cats toolchain
# ---------------------------------------------------------------------------
if [[ -d "$VENDOR/.git" ]]; then
  say "CatSniffer-Tools already present — leaving it alone."
elif [[ -d "$VENDOR" ]]; then
  say "CatSniffer-Tools present (vendored copy, no .git) — leaving it alone."
else
  say "Fetching Electronic Cats CatSniffer-Tools at $PIN ..."
  git clone --quiet "$UPSTREAM" "$VENDOR"
  git -C "$VENDOR" checkout --quiet "$PIN"
  say "  -> $VENDOR"
fi

PYCAT="$VENDOR/pycatsniffer_bv3"
[[ -d "$PYCAT" ]] || die "pycatsniffer_bv3 missing under $VENDOR — the clone looks wrong."

# ---------------------------------------------------------------------------
# 2. One venv
# ---------------------------------------------------------------------------
# The lab this came from needed two venvs, because pycatsniffer pins click 8.1 /
# typer 0.9 and the Home Assistant stack alongside it wanted newer. Nothing here
# imports zigpy or Home Assistant, so the conflict is gone and one venv is enough.
if [[ ! -x "$HERE/.venv/bin/python" ]]; then
  say "Creating .venv ..."
  python3 -m venv "$HERE/.venv"
fi

say "Installing dependencies ..."
"$HERE/.venv/bin/pip" install --quiet --upgrade pip
"$HERE/.venv/bin/pip" install --quiet -r "$PYCAT/requirements.txt"

# catnip_uploader is the only supported way to write firmware to the CC1352P7.
# Driving the raw bootloader by hand bricks the radio.
if [[ -f "$VENDOR/catnip_uploader/requirements.txt" ]]; then
  "$HERE/.venv/bin/pip" install --quiet -r "$VENDOR/catnip_uploader/requirements.txt" || true
fi

mkdir -p "$HERE/captures"

# Seed the console with the sample captures so a fresh install renders a real
# chart instead of an empty one. captures/ is gitignored, so this is a copy into
# the technician's own working directory, not a committed file.
for s in "$HERE"/samples/*.pcap; do
  [[ -e "$s" ]] || break
  [[ -e "$HERE/captures/$(basename "$s")" ]] || cp "$s" "$HERE/captures/"
done

# ---------------------------------------------------------------------------
# 3. Report
# ---------------------------------------------------------------------------
say "Done."
cat <<EOF

  Next:

    ./zigscan identify     what is plugged in, and what firmware is on it
    ./zigscan survey       open the console at http://127.0.0.1:8477

  The radio needs TI sniffer firmware to hear anything. If ./zigscan identify
  says the role is unknown or coordinator, see docs/HARDWARE.md before blaming
  the antenna.

EOF
