#!/usr/bin/env bash
# Prepare the Python tooling used by `make test`. The Supervisor environment
# itself is set up by `devcontainer_bootstrap` / `supervisor_run`.
set -euo pipefail

if ! command -v python3 >/dev/null; then
  echo "python3 is not available in this devcontainer image."
  echo "The Supervisor workflow still works; run tests on the host with 'make test'."
  exit 0
fi

make venv
./scripts/dev_fixture.sh

cat <<'MSG'

Domácí manuál development environment ready.

  make test            run the automated tests
  make build && make up  fast container-only loop on http://localhost:8099
  supervisor_run       start Supervisor + Home Assistant on http://localhost:7123
                       (or run the "Start Home Assistant" task)

MSG
