# Git Workflow Rules

## Serena Activation

Before starting code investigation (reading symbols, exploring architecture),
check if Serena is activated. If not, activate it:

```bash
mcp__serena__activate_project("/home/yamakii/workspace/claude_workspace/garmin-performance-analysis")
```

This applies to all phases: investigation, planning, and implementation.
Serena's symbolic tools (find_symbol, get_symbols_overview, find_referencing_symbols)
provide more precise code navigation than Glob/Grep alone.

## Branch Strategy

- **Planning**: Main branch (no worktree needed)
- **Implementation**: Git worktree mandatory
- **Completion**: Merge to main, remove worktree

## Worktree Setup

```bash
git worktree add -b feature/name ../garmin-feature-name main
cd ../garmin-feature-name
uv sync --extra dev
direnv allow

# MANDATORY: Activate Serena for code editing
mcp__serena__activate_project("/absolute/path/to/worktree")
```

## Commit Convention

Conventional Commits format with Co-Authored-By:

```bash
git commit -m "feat: description

Co-Authored-By: Claude <noreply@anthropic.com>"
```

## After Merge

```bash
cd /path/to/main
git worktree remove ../garmin-feature-name
```
