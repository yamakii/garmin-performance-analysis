# GitHub MCP Only

## GitHub 操作は `mcp__github__*` ツールを使用すること

`gh` CLI は deny 設定でブロック済み。全 GitHub 操作は MCP ツール経由で行う。

## コマンド対応表

| gh CLI | MCP ツール |
|--------|-----------|
| `gh issue view N` | `mcp__github__get_issue(owner, repo, issue_number)` |
| `gh issue create` | `mcp__github__create_issue(owner, repo, title, body, labels)` |
| `gh issue edit N` | `mcp__github__update_issue(owner, repo, issue_number, ...)` |
| `gh issue close N` | `mcp__github__update_issue(owner, repo, issue_number, state="closed")` |
| `gh issue list` | `mcp__github__list_issues(owner, repo, state, labels)` |
| `gh pr view N` | `mcp__github__get_pull_request(owner, repo, pull_number)` |
| `gh pr create` | `mcp__github__create_pull_request(owner, repo, title, head, base, body)` |
| `gh pr merge N` | `mcp__github__merge_pull_request(owner, repo, pull_number, merge_method)` |
| `gh pr checks N` | `mcp__github__get_pull_request_status(owner, repo, pull_number)` |

## リポジトリ情報

全 MCP ツール呼び出しで使用:
- `owner`: `"yamakii"`
- `repo`: `"garmin-performance-analysis"`

## ブランチ削除

`merge_pull_request` に `--delete-branch` 相当はない。GitHub リポジトリ設定で auto-delete が有効なため不要。
