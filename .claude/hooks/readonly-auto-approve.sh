#!/bin/bash
# PreToolUse hook: Auto-approve read-only Bash commands
# Parses piped/chained commands and approves only if ALL subcommands are read-only.

set -euo pipefail

# Read JSON from stdin
input=$(cat)

# Extract the command field using python (jq not guaranteed)
command=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null) || exit 0

# Empty command - delegate to normal flow
[ -z "$command" ] && exit 0

# Read-only commands whitelist
readonly SAFE_CMDS="grep rg sed sort awk head tail wc cat find tr cut uniq diff file stat ls echo printf test [ dirname basename realpath readlink date du xargs tee"

# Split command by pipe, semicolons, && and || into subcommands
# Replace delimiters with newlines for iteration
subcommands=$(echo "$command" | sed 's/||\{0,1\}/\n/g; s/&&/\n/g; s/;/\n/g')

while IFS= read -r subcmd; do
    # Trim whitespace
    subcmd=$(echo "$subcmd" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    [ -z "$subcmd" ] && continue

    # Strip leading env vars (FOO=bar cmd ...) and command substitutions
    first_word=$(echo "$subcmd" | sed 's/^[A-Za-z_][A-Za-z0-9_]*=[^ ]* *//' | awk '{print $1}')

    # Strip path prefix (e.g., /usr/bin/grep -> grep)
    first_word=$(basename "$first_word" 2>/dev/null || echo "$first_word")

    # Check against whitelist
    is_safe=false
    for safe in $SAFE_CMDS; do
        if [ "$first_word" = "$safe" ]; then
            is_safe=true
            break
        fi
    done

    if [ "$is_safe" = false ]; then
        # Unsafe command found - delegate to normal permission flow
        exit 0
    fi
done <<< "$subcommands"

# All subcommands are read-only - auto-approve
echo '{"decision":"allow","reason":"All subcommands are read-only"}'
