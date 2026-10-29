#!/bin/sh
# One-line installer: curl -sSL https://raw.githubusercontent.com/mrcoconut0101/CircuitLordVRModInstaller-on-frame/main/linux/install-frame.sh | sh
set -e
URL="https://raw.githubusercontent.com/mrcoconut0101/CircuitLordVRModInstaller-on-frame/main/linux/install-frame.py"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
curl -fsSL "$URL" -o "$TMP/install-frame.py"
python3 "$TMP/install-frame.py" "$@"
