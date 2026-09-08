#!/usr/bin/env bash
# `uv` front door for the sandbox image (#1047): installed as /usr/local/bin/uv,
# with the real binary at /usr/local/lib/uv/uv.
#
# Unless the caller already set UV_PROJECT_ENVIRONMENT, derive it from the
# checkout the command targets (--directory / --project / cwd) via
# docker/lib/uv-venv.sh, so every checkout and package gets its own venv and a
# worktree command can never touch the MCP server's environment. Outside a git
# checkout the variable stays unset and uv behaves exactly as upstream.
#
# UV_REAL / UV_VENV_LIB exist for the self-test (scripts/tests/test-uv-venv.sh).
set -u

UV_REAL="${UV_REAL:-/usr/local/lib/uv/uv}"
UV_VENV_LIB="${UV_VENV_LIB:-/usr/local/lib/sandbox/uv-venv.sh}"

if [ -z "${UV_PROJECT_ENVIRONMENT:-}" ] && [ -r "$UV_VENV_LIB" ]; then
  # shellcheck source=lib/uv-venv.sh
  . "$UV_VENV_LIB"
  dir="$(uv_project_dir "$@")"
  if venv="$(uv_venv_path "$dir")"; then
    export UV_PROJECT_ENVIRONMENT="$venv"
  fi
fi

exec "$UV_REAL" "$@"
