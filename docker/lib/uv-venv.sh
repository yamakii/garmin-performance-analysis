#!/usr/bin/env bash
# Pure helpers that map a directory to its uv virtualenv (#1047).
#
# Sourced by docker/uv-wrapper.sh (installed as /usr/local/bin/uv in the sandbox
# image), by scripts/ci-check.sh, and by scripts/tests/test-uv-venv.sh. Keep it
# side-effect free so the logic stays unit-testable without docker.
#
# Why: the image used to set one global UV_PROJECT_ENVIRONMENT for every checkout
# and both workspace packages, so a `uv run --directory <worktree>` re-pointed the
# MCP server's editable install at the worktree (reload_server crashed after the
# worktree was removed) and two `uv sync` calls evicted each other's extras. One
# venv per (checkout, package) removes the shared mutable resource. The venvs
# stay OUTSIDE the bind-mounted repo so a container venv never collides with the
# host's .venv.

# uv_venv_base
# Prints the directory that holds all per-checkout venvs.
uv_venv_base() {
  printf '%s\n' "${UV_VENV_BASE:-${HOME:-/home/claude}/uv-venvs}"
}

# uv_venv_path DIR
# Prints "<base>/<cksum of checkout root>-<server|web>" for any DIR inside a git
# checkout: DIR under packages/garmin-web → web, everything else (the root
# workspace, packages/garmin-mcp-server, scratch dirs) → server. Returns 1 and
# prints nothing when DIR is not inside a git checkout. `cksum` keeps the name
# short — a long venv path would overflow the 127-byte shebang limit in bin/.
uv_venv_path() {
  local dir="$1" abs root id pkg
  abs="$(cd "$dir" 2>/dev/null && pwd -P)" || return 1
  root="$(git -C "$abs" rev-parse --show-toplevel 2>/dev/null)" || return 1
  id="$(printf '%s' "$root" | cksum | cut -d' ' -f1)"
  case "$abs/" in
    "$root"/packages/garmin-web/*) pkg=web ;;
    *) pkg=server ;;
  esac
  printf '%s/%s-%s\n' "$(uv_venv_base)" "$id" "$pkg"
}

# uv_project_dir UV_ARGS...
# Prints the project directory a uv invocation refers to: the value of
# --directory / --project (either `--flag X` or `--flag=X`), else the cwd.
uv_project_dir() {
  local prev="" a
  for a in "$@"; do
    case "$a" in
      --directory=*|--project=*) printf '%s\n' "${a#*=}"; return 0 ;;
    esac
    case "$prev" in
      --directory|--project) printf '%s\n' "$a"; return 0 ;;
    esac
    prev="$a"
  done
  pwd
}
