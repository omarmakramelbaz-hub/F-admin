#!/usr/bin/env bash
set -euo pipefail
umask 077

test "$(id -u)" -eq 0
test "$(hostname -s)" = srv1836524
test -d /home/fasakha/public_html
test "$#" -eq 3
webview_revision=$1
webview_installer_sha=$2
webview_manifest_sha=$3
[[ "$webview_revision" =~ ^[a-f0-9]{40}$ ]]
[[ "$webview_installer_sha" =~ ^[a-f0-9]{64}$ ]]
[[ "$webview_manifest_sha" =~ ^[a-f0-9]{64}$ ]]

webview_inputs=$(mktemp -d /var/tmp/fasakhansta-f-admin-webview-inputs.XXXXXXXX)
trap 'rm -f -- "$webview_inputs/install.py"; rmdir -- "$webview_inputs"' EXIT
chmod 0700 "$webview_inputs"
curl --fail --silent --show-error --location \
  --proto '=https' --proto-redir '=https' --max-time 60 \
  "https://raw.githubusercontent.com/omarmakramelbaz-hub/F-admin/$webview_revision/deployment/webview-20261111/install.py" \
  -o "$webview_inputs/install.py"
printf '%s  %s\n' "$webview_installer_sha" "$webview_inputs/install.py" | sha256sum --check --status
/usr/bin/python3 "$webview_inputs/install.py" --revision "$webview_revision" --manifest-sha256 "$webview_manifest_sha"
