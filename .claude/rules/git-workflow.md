# Git Workflow Rules

## Serena Activation (MANDATORY)

**MUST activate Serena BEFORE any code investigation**, including plan mode exploration.
This is the FIRST step in any task involving code understanding.

```
mcp__serena__activate_project("/home/yamakii/workspace/garmin-performance-analysis")
```

### When to activate
- **Plan mode Phase 1 (Initial Understanding)**: MUST activate before launching Explore agents
- **Planning phase**: MUST activate before project-planner agent
- **Implementation phase**: MUST activate for worktree path

### Why
Serena's symbolic tools (`find_symbol`, `get_symbols_overview`, `find_referencing_symbols`)
provide precise code navigation. Glob/Grep alone misses symbol relationships and type information.

### Fallback
If Serena activation fails, use Glob/Grep as fallback but note the limitation in your output.

### Stale Session Recovery
- Re-activate Serena with the same path: `mcp__serena__activate_project("/path/to/project")`
- If still broken: `/mcp` → restart serena server
- For worktrees: always use the worktree's absolute path, not the main repo path

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
