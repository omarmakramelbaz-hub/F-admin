#!/usr/bin/env bash
set -euo pipefail
umask 077

test "$(id -u)" -eq 0
test "$(hostname -s)" = srv1836524
test -d /home/fasakha/public_html
test "$#" -eq 3
opening_revision=$1
opening_installer_sha=$2
opening_manifest_sha=$3
[[ "$opening_revision" =~ ^[a-f0-9]{40}$ ]]
[[ "$opening_installer_sha" =~ ^[a-f0-9]{64}$ ]]
[[ "$opening_manifest_sha" =~ ^[a-f0-9]{64}$ ]]

opening_inputs=$(mktemp -d /var/tmp/fasakhansta-f-admin-webview-opening-inputs.XXXXXXXX)
trap 'rm -f -- "$opening_inputs/install.py"; rmdir -- "$opening_inputs"' EXIT
chmod 0700 "$opening_inputs"
curl --fail --silent --show-error --location \
  --proto '=https' --proto-redir '=https' --max-time 60 \
  "https://raw.githubusercontent.com/omarmakramelbaz-hub/F-admin/$opening_revision/deployment/webview-opening-20261111/install.py" \
  -o "$opening_inputs/install.py"
printf '%s  %s\n' "$opening_installer_sha" "$opening_inputs/install.py" | sha256sum --check --status
/usr/bin/python3 "$opening_inputs/install.py" --revision "$opening_revision" --manifest-sha256 "$opening_manifest_sha"
