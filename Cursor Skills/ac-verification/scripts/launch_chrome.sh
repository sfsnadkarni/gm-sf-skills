#!/usr/bin/env bash
# Launch (or reuse) a dedicated Chrome with remote debugging for AC verification.
#
# Usage: launch_chrome.sh [port] [profile_dir] [url]
#   port         default 9222
#   profile_dir  default ~/.ac-verification-chrome  (separate profile; dev's
#                normal browsing is untouched)
#   url          optional page to open (e.g. the org login URL)
#
# Prints one of: ALREADY_UP | LAUNCHED | FAILED_TO_START
# Exit code 0 if the debug port is reachable, non-zero otherwise.
#
# NOTE: launching a GUI app may require running outside the sandbox
# (required_permissions: ["all"]). If blocked, ask the dev to run this
# command in their own Terminal instead.
set -u

PORT="${1:-9222}"
PROFILE="${2:-$HOME/.ac-verification-chrome}"
URL="${3:-}"
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

if curl -s --max-time 3 "http://localhost:${PORT}/json/version" >/dev/null 2>&1; then
  echo "ALREADY_UP on ${PORT}"
  exit 0
fi

if [ ! -x "$CHROME" ]; then
  echo "FAILED_TO_START: Chrome not found at '$CHROME'"
  exit 1
fi

if [ -n "$URL" ]; then
  "$CHROME" --remote-debugging-port="${PORT}" --user-data-dir="${PROFILE}" "$URL" >/dev/null 2>&1 &
else
  "$CHROME" --remote-debugging-port="${PORT}" --user-data-dir="${PROFILE}" >/dev/null 2>&1 &
fi

for _ in $(seq 1 20); do
  if curl -s --max-time 2 "http://localhost:${PORT}/json/version" >/dev/null 2>&1; then
    echo "LAUNCHED on ${PORT}"
    exit 0
  fi
  sleep 0.5
done

echo "FAILED_TO_START: port ${PORT} not reachable after launch"
exit 1
