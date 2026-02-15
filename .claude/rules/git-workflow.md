# Git Workflow Rules

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
