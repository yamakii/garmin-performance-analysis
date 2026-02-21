# Git Workflow Rules

## Serena Activation (MANDATORY)

**MUST activate Serena BEFORE any code investigation**, including plan mode exploration.
This is the FIRST step in any task involving code understanding.

```
mcp__serena__activate_project("/home/yamakii/workspace/garmin-performance-analysis")
```

### When to activate
- **Plan mode Phase 1 (Initial Understanding)**: MUST activate before launching Explore agents
- **Decompose phase**: MUST activate before `/decompose` command (code exploration)
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

## Branch Strategy (STRICT — NO EXCEPTIONS)

- **Planning**: Main branch (read-only exploration, no edits)
- **Implementation**: Git worktree MANDATORY — ユーザーが明示的に「worktree不要」と指示しない限り、必ずworktreeを作成する。曖昧な判断で省略してはならない。
- **Completion**: Merge to main, remove worktree

**禁止:** main ブランチ上での直接的なコード編集（ルールファイル `.claude/rules/` のみ例外）

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

## Commit Discipline

各コミットは**単一の関心事**のみ含めること:

- feat: 1つの機能追加のみ
- fix: 1つのバグ修正のみ
- test: テスト追加/修正のみ
- docs: ドキュメント変更のみ
- refactor: リファクタリングのみ

**禁止パターン:**
- feat + fix を1コミットに混ぜる
- コード変更 + 無関係なルール更新を混ぜる
- 複数の独立した機能を1コミットにまとめる

**判断基準:** コミットメッセージに "and" や "+" が必要なら分割すべき。

## After Merge

```bash
cd /path/to/main
git worktree remove ../garmin-feature-name
```
