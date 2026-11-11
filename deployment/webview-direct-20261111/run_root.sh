#!/usr/bin/env bash
set -euo pipefail
umask 077

test "$(id -u)" -eq 0
test "$(hostname -s)" = srv1836524
test -d /home/fasakha/public_html
test "$#" -eq 3
direct_webview_revision=$1
direct_webview_installer_sha=$2
direct_webview_manifest_sha=$3
[[ "$direct_webview_revision" =~ ^[a-f0-9]{40}$ ]]
[[ "$direct_webview_installer_sha" =~ ^[a-f0-9]{64}$ ]]
[[ "$direct_webview_manifest_sha" =~ ^[a-f0-9]{64}$ ]]

direct_webview_inputs=$(mktemp -d /var/tmp/fasakhansta-f-admin-direct-webview-inputs.XXXXXXXX)
trap 'rm -f -- "$direct_webview_inputs/install.py"; rmdir -- "$direct_webview_inputs"' EXIT
chmod 0700 "$direct_webview_inputs"
curl --fail --silent --show-error --proto '=https' \
  --connect-timeout 15 --max-time 60 --max-filesize 131072 \
  "https://raw.githubusercontent.com/omarmakramelbaz-hub/F-admin/$direct_webview_revision/deployment/webview-direct-20261111/install.py" \
  -o "$direct_webview_inputs/install.py"
printf '%s  %s\n' "$direct_webview_installer_sha" "$direct_webview_inputs/install.py" | sha256sum --check --status
/usr/bin/python3 "$direct_webview_inputs/install.py" --revision "$direct_webview_revision" --manifest-sha256 "$direct_webview_manifest_sha"
