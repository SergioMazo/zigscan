#!/usr/bin/env bash
#
# Build zigscan.app and a .dmg a technician can install.
#
# Unsigned by default. macOS will refuse to open an unsigned app on first launch
# and the technician has to right-click -> Open once; that is documented in the
# manual. Set ZIGSCAN_SIGN_ID to a Developer ID Application identity to sign,
# and ZIGSCAN_NOTARY_PROFILE to a stored notarytool profile to notarize, and
# that friction disappears.
#
#   ./build-macos.sh
#   ZIGSCAN_SIGN_ID="Developer ID Application: Name (TEAMID)" ./build-macos.sh
#
# Requires the dev virtualenv:  ./setup.sh && ./.venv/bin/pip install pyinstaller

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/.venv/bin/python"
APP="$HERE/dist/zigscan.app"
DMG="$HERE/dist/zigscan.dmg"

say() { printf '\n  %s\n' "$*"; }
die() { printf '\nERROR: %s\n\n' "$*" >&2; exit 1; }

[[ -x "$PY" ]] || die "No virtualenv. Run ./setup.sh first."
"$PY" -c "import PyInstaller" 2>/dev/null || die "PyInstaller missing. ./.venv/bin/pip install pyinstaller"

# The toolchain is fetched by setup.sh, not committed. Building without it
# produces an app that launches and then cannot capture — the exact failure this
# check exists to prevent.
[[ -d "$HERE/tools/catsniffer-tools/pycatsniffer_bv3" ]] \
  || die "pycatsniffer not found. Run ./setup.sh first."

say "Cleaning previous build ..."
rm -rf "$HERE/build" "$HERE/dist"

say "Building zigscan.app ..."
"$PY" -m PyInstaller --noconfirm --clean "$HERE/zigscan.spec"

[[ -d "$APP" ]] || die "PyInstaller finished but $APP is missing."

# Upstream's checkout may contain empty developer dump files. They are not
# runtime dependencies and no capture artifact belongs in a public bundle.
say "Removing vendored capture artifacts ..."
find "$APP/Contents/Resources/tools/catsniffer-tools" -type f -name "*.pcap" -delete

# iCloud Drive, Finder and the quarantine flag all attach extended attributes,
# and codesign refuses to touch a bundle that carries them — "resource fork,
# Finder information, or similar detritus not allowed". It bites even the
# ad-hoc signature PyInstaller applies at the end of its own build, so strip
# them before any signing is attempted.
say "Stripping extended attributes ..."
xattr -cr "$APP"

# ---------------------------------------------------------------------------
# Signing — optional, and the only part that needs an Apple account
# ---------------------------------------------------------------------------
if [[ -n "${ZIGSCAN_SIGN_ID:-}" ]]; then
  say "Signing with $ZIGSCAN_SIGN_ID ..."
  # --deep is deprecated and unreliable for nested code; sign inside-out.
  find "$APP/Contents" -type f \( -name "*.so" -o -name "*.dylib" \) -print0 \
    | xargs -0 -I{} codesign --force --timestamp --options runtime \
        --sign "$ZIGSCAN_SIGN_ID" {}
  codesign --force --timestamp --options runtime --sign "$ZIGSCAN_SIGN_ID" "$APP"
  codesign --verify --strict --verbose=2 "$APP"

  if [[ -n "${ZIGSCAN_NOTARY_PROFILE:-}" ]]; then
    say "Notarizing ..."
    ditto -c -k --keepParent "$APP" "$HERE/dist/zigscan-notarize.zip"
    xcrun notarytool submit "$HERE/dist/zigscan-notarize.zip" \
      --keychain-profile "$ZIGSCAN_NOTARY_PROFILE" --wait
    xcrun stapler staple "$APP"
    rm -f "$HERE/dist/zigscan-notarize.zip"
  fi
else
  say "No Developer ID. Applying an ad-hoc seal after bundle cleanup ..."
  codesign --force --sign - "$APP"
  codesign --verify --deep --strict "$APP"
  say "First launch still needs right-click -> Open (see docs/MANUAL.md)."
fi

# ---------------------------------------------------------------------------
# Disk image
# ---------------------------------------------------------------------------
say "Building zigscan.dmg ..."
STAGE="$(mktemp -d)"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"
hdiutil create -volname "zigscan" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"

say "Done."
printf '\n    %s\n    %s\n\n' "$APP" "$DMG"
du -sh "$APP" "$DMG" | sed 's/^/    /'
echo
