#!/bin/bash
# Auto-format + type-check Python files after Claude Code / Serena edits.
# Silent on success (exit 0 + no output = invisible in normal mode); mypy
# errors block (exit 2 = Claude must fix before proceeding).
#
# Scope: only files under <checkout>/packages/** of the git checkout the file
# lives in (main or a worktree). Scratch scripts and files outside a checkout are
# skipped. Tools run via `uv run --no-sync --directory <package>` so the hook
# (a) never re-syncs the shared UV_PROJECT_ENVIRONMENT venv — running `uv run`
# from the main checkout used to re-lock the env under a worktree's in-progress
# ci-check — and (b) type-checks against the package config of the file's own
# checkout instead of main's.

INPUT=$(cat)

# Claude built-in tools use "file_path" (absolute), Serena uses "relative_path"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
if [[ -z "$FILE_PATH" ]]; then
  REL_PATH=$(echo "$INPUT" | jq -r '.tool_input.relative_path // empty')
  if [[ -n "$REL_PATH" ]]; then
    FILE_PATH="${CLAUDE_PROJECT_DIR}/${REL_PATH}"
  fi
fi

# Only format .py files that exist
[[ "$FILE_PATH" =~ \.py$ ]] || exit 0
[[ -f "$FILE_PATH" ]] || exit 0
FILE_PATH=$(realpath "$FILE_PATH" 2>/dev/null) || exit 0

# Only project code: <checkout>/packages/<package>/** (main or any worktree)
ROOT=$(git -C "$(dirname "$FILE_PATH")" rev-parse --show-toplevel 2>/dev/null) || exit 0
[[ -n "$ROOT" ]] || exit 0
case "$FILE_PATH" in
  "$ROOT"/packages/garmin-mcp-server/*) PKG="$ROOT/packages/garmin-mcp-server" ;;
  "$ROOT"/packages/garmin-web/*)        PKG="$ROOT/packages/garmin-web" ;;
  *) exit 0 ;;
esac

run() { uv run --no-sync --directory "$PKG" "$@"; }

# Formatters: silent, and skipped when the tool is not in the current env.
run black --version >/dev/null 2>&1 && run black --quiet "$FILE_PATH" 2>/dev/null
run ruff --version >/dev/null 2>&1 && run ruff check --fix --quiet "$FILE_PATH" 2>/dev/null

# Type check — block on errors. Skip silently if mypy is not installed.
run mypy --version >/dev/null 2>&1 || exit 0
MYPY_OUTPUT=$(run mypy --no-error-summary --no-pretty "$FILE_PATH" 2>/dev/null)
MYPY_EXIT=$?

if [[ $MYPY_EXIT -ne 0 ]]; then
  echo "$MYPY_OUTPUT" >&2
  echo "(mypy ran in $PKG against the current shared venv; if these errors look stale, run: uv sync --directory $PKG --extra dev)" >&2
  exit 2
fi

exit 0
