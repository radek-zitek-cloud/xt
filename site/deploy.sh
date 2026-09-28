#!/bin/sh
# Deploys this folder to https://zitek.cloud/xt/ : the Hestia web root of zitek.cloud on orlik,
# over the tailnet (`ssh orlik`, sudo needed because the web root belongs to radekzitek).
# nginx serves the files directly; no server configuration is involved.
set -eu
here=$(cd "$(dirname "$0")" && pwd)
dest=/home/radekzitek/web/zitek.cloud/public_html/xt
rsync -rtv --delete --exclude README.md --exclude deploy.sh --rsync-path="sudo -n rsync" "$here/" "orlik:$dest/"
ssh orlik "sudo -n chown -R radekzitek:radekzitek $dest && sudo -n find $dest -type d -exec chmod 755 {} + && sudo -n find $dest -type f -exec chmod 644 {} +"
curl -s -o /dev/null -w "https://zitek.cloud/xt/ -> %{http_code}\n" https://zitek.cloud/xt/
