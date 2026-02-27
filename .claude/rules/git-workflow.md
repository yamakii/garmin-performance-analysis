# Git Workflow Rules

## Serena Activation

Activate Serena BEFORE code investigation (plan mode, decompose, implementation):
```
mcp__serena__activate_project("/home/yamakii/workspace/garmin-performance-analysis")
```
- Explore agents activate separately (see `explore-agent-serena.md`)
- Fallback: Glob/Grep if activation fails

### Stale Session Recovery
- Serena: `mcp__serena__activate_project("/path/to/project")`
- garmin-db: `mcp__garmin-db__reload_server(server_dir="...")` (省略で default 復帰)
- If still broken: `/mcp` → restart server

## Branch Strategy

- **Code changes** (`packages/`, `tests/`): worktree MANDATORY
- **Rules/docs** (`.claude/rules/`, `docs/`, `CLAUDE.md`): main OK
- **Planning**: main branch (read-only)

### Worktree Setup
```bash
git worktree add -b feature/name ../garmin-feature-name main
cd ../garmin-feature-name && uv sync --extra dev && direnv allow
mcp__serena__activate_project("/absolute/path/to/worktree")
mcp__garmin-db__reload_server(server_dir="/absolute/path/to/worktree/packages/garmin-mcp-server")
```

### After Merge
```bash
git worktree remove ../garmin-feature-name
```

## Commit Convention

Conventional Commits + Co-Authored-By. 各コミットは**単一の関心事**のみ。

判断基準: メッセージに "and" や "+" が必要なら分割すべき。
