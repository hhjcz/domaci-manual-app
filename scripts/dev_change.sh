#!/usr/bin/env bash
# Push a change to the local fixture repository, the way a developer would push
# to the real documentation repository. The running app should pick it up.
set -euo pipefail
cd "$(dirname "$0")/.."

work=.dev/docs-work
[ -d "$work" ] || { echo "Run scripts/dev_fixture.sh first" >&2; exit 1; }

stamp="$(date --iso-8601=seconds)"
printf '\n## Changed at %s\n\nThis line was pushed by scripts/dev_change.sh.\n' "$stamp" \
  >> "$work/heating/heat-pump.md"

git -C "$work" add -A
git -C "$work" commit -qm "Update heat pump notes at $stamp"
git -C "$work" push -q origin main
echo "Pushed: $(git -C "$work" log -1 --format='%h %s')"
