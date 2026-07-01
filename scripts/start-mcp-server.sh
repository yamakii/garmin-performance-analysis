#!/usr/bin/env bash
set -euo pipefail

# Resolve the repo root regardless of the cwd we were spawned with, so the
# server launches correctly under headless / subdirectory contexts (where the
# spawn cwd is not guaranteed to be the repo root). Claude Code injects
# CLAUDE_PROJECT_DIR into a project-scoped MCP server's env; fall back to the
# script's own location when it is absent (e.g. manual invocation).
ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"

# Stable shim: always launch the bundled server package via a single exec.
# Worktree development no longer relies on an override-dir mechanism — code
# under development is validated in subprocess (`uv run --directory <worktree>`)
# rather than swapped into the live launcher. reload_server restarts the worker
# in place; it never reads an override file.
exec uv run --directory packages/garmin-mcp-server garmin-mcp-server
