#!/usr/bin/env bash
set -euo pipefail

# Stable shim: always launch the bundled server package via a single exec.
# Worktree development no longer relies on an override-dir mechanism — code
# under development is validated in subprocess (`uv run --directory <worktree>`)
# rather than swapped into the live launcher. reload_server restarts the worker
# in place; it never reads an override file.
exec uv run --directory packages/garmin-mcp-server garmin-mcp-server
