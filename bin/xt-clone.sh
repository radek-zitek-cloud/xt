#!/bin/sh
# xt-clone.sh [--no-start] <team-name> [directory]
#
# Create a new xt team: clone xt from GitHub into <directory> (default ./<team-name>), trust its
# mise config, run `xt init` with the team name as both team and Herdr session name, start that
# Herdr session in the background if it isn't running, run `xt up` (supervisor + liaison), and
# attach to the session. --no-start stops after `xt init`.
set -eu

REPO="${XT_REPO:-radek-zitek-cloud/xt}"

usage() {
  echo "usage: xt-clone.sh [--no-start] <team-name> [directory]" >&2
  exit 2
}

start=1
if [ "${1:-}" = "--no-start" ]; then
  start=0
  shift
fi
[ $# -ge 1 ] && [ $# -le 2 ] || usage
team=$1
case "$team" in
  "" | -* | *[!a-z0-9-]*)
    echo "team name: lowercase letters, digits and dashes only (it's also the Herdr session name)" >&2
    exit 2
    ;;
esac
dir=${2:-$PWD/$team}
if [ -e "$dir" ]; then
  echo "$dir already exists; pick another name or directory" >&2
  exit 1
fi
for tool in git herdr mise; do
  command -v "$tool" >/dev/null 2>&1 || { echo "missing prerequisite: $tool" >&2; exit 1; }
done

echo "==> cloning $REPO into $dir"
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  gh repo clone "$REPO" "$dir" -- --quiet
else
  git clone --quiet "https://github.com/$REPO.git" "$dir"
fi
cd "$dir"

echo "==> trusting mise config"
mise trust --quiet

echo "==> xt init"
# Call the clone's own xt: mise only adds bin/ to PATH in shells that have it activated.
./bin/xt init --name "$team" --session "$team"

if [ "$start" -eq 0 ]; then
  echo "==> done (not started). Start later: herdr --session $team, then run xt in $dir"
  exit 0
fi

session_status() {
  herdr session list 2>/dev/null | awk -v t="$1" '$1 == t { print $2 }'
}

if [ "$(session_status "$team")" != "running" ]; then
  echo "==> starting Herdr session $team in the background"
  setsid herdr --session "$team" server >/dev/null 2>&1 < /dev/null &
  i=0
  while [ "$(session_status "$team")" != "running" ]; do
    i=$((i + 1))
    [ "$i" -le 50 ] || { echo "Herdr session $team didn't start" >&2; exit 1; }
    sleep 0.2
  done
fi

echo "==> xt up"
./bin/xt up

if [ -n "${HERDR_ENV:-}" ]; then
  echo "==> you're inside Herdr already; switch to the team with: herdr session attach $team"
else
  echo "==> attaching to Herdr session $team (the liaison has its own workspace)"
  exec herdr --session "$team"
fi
