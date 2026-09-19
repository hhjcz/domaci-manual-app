#!/usr/bin/env bash
# Create a local Git fixture that stands in for the private documentation
# repository, so the whole clone/pull path can be exercised without GitHub.
#
#   .dev/docs.git   bare "remote"
#   .dev/docs-work  working clone used to push changes
set -euo pipefail
cd "$(dirname "$0")/.."

dev=.dev
rm -rf "$dev/docs.git" "$dev/docs-work"
mkdir -p "$dev"

git init -q --bare -b main "$dev/docs.git"
git init -q -b main "$dev/docs-work"
cp -r sample-docs/. "$dev/docs-work/"

git -C "$dev/docs-work" config user.email dev@example.invalid
git -C "$dev/docs-work" config user.name "Domaci manual dev"
git -C "$dev/docs-work" add -A
git -C "$dev/docs-work" commit -qm "Initial sample documentation"
git -C "$dev/docs-work" remote add origin "$PWD/$dev/docs.git"
git -C "$dev/docs-work" push -q origin main

mkdir -p "$dev/data"
# The absolute host path. `make up` bind-mounts the bare repo at this very
# path inside the container, so host and container use the same URL.
repo_url="file://$PWD/$dev/docs.git"

cat > "$dev/data/options.json" <<JSON
{
  "repository": "$repo_url",
  "branch": "main",
  "docs_subdir": "",
  "sync_interval": 1,
  "site_name": "Domácí manuál",
  "language": "en",
  "strict_host_key_checking": true,
  "extra_known_hosts": [],
  "deploy_key": "",
  "log_level": "debug"
}
JSON

echo "Fixture ready:"
echo "  remote : $PWD/$dev/docs.git"
echo "  clone  : $PWD/$dev/docs-work"
echo "  options: $PWD/$dev/data/options.json"
