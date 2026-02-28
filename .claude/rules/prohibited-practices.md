# Prohibited Practices

## Development

- Edit code without Serena MCP
- Implement on main branch (use worktree for code changes)
- `git worktree remove --force` without checking status
- Push directly to main (branch protection enabled — all changes require PR)
- Force push to main/master
- 複数の無関係な変更を1コミットに混在させる

## Database

- Delete database without user approval (`rm *.duckdb`, `--delete-db`)
- Propose `--delete-db` as first solution for errors

## Configuration

- Put rules in CLAUDE.md directly (use `.claude/rules/`)
- Create rule files outside `.claude/rules/`

## Testing

- Tests depending on real production data
