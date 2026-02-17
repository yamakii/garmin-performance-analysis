#!/bin/bash
# Auto-format Python files after Claude Code / Serena edits

INPUT=$(cat)

# Claude built-in tools use "file_path" (absolute), Serena uses "relative_path"
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
if [[ -z "$FILE_PATH" ]]; then
  REL_PATH=$(echo "$INPUT" | jq -r '.tool_input.relative_path // empty')
  if [[ -n "$REL_PATH" ]]; then
    FILE_PATH="${CLAUDE_PROJECT_DIR}/${REL_PATH}"
  fi
fi

# Only format .py files
if [[ ! "$FILE_PATH" =~ \.py$ ]]; then
  exit 0
fi

# Check file exists
if [[ ! -f "$FILE_PATH" ]]; then
  exit 0
fi

# Run formatters (black first, then ruff fix)
echo "[hook] Formatting: $(basename "$FILE_PATH")" >&2
uv run black --quiet "$FILE_PATH" 2>/dev/null
uv run ruff check --fix --quiet "$FILE_PATH" 2>/dev/null

# Type check (advisory, does not block)
uv run mypy --no-error-summary --no-pretty "$FILE_PATH" 2>/dev/null \
  && echo "[hook] Types OK" >&2 \
  || echo "[hook] Type warnings: uv run mypy $FILE_PATH" >&2

echo "[hook] Done" >&2

exit 0
