# Worktree Commands

## `cd <path> && ...` を使わない

worktree 内でコマンドを実行する際、`cd <path> && <cmd>` は compound コマンドとして Claude Code が毎回承認を求める。各ツールのディレクトリ指定オプションを使う。

### git 操作 — `git -C <path>`

| 用途 | コマンド |
|------|---------|
| ステージ | `git -C <path> add file1 file2` |
| コミット | `git -C <path> commit -m "msg"` |
| 状態確認 | `git -C <path> status` |
| 差分 | `git -C <path> diff` |
| ログ | `git -C <path> log --oneline -5` |
| プッシュ | `git -C <path> push -u origin branch` |
| ブランチ作成 | `git -C <path> checkout -b branch` |
| stash | `git -C <path> stash` |
| fetch | `git -C <path> fetch origin` |

### uv / pytest / ruff / pre-commit — `--directory`

| 用途 | コマンド |
|------|---------|
| テスト | `uv run --directory <path> pytest -m unit -v` |
| lint | `uv run --directory <path> ruff check src/` |
| pre-commit | `uv run --directory <path> pre-commit run --all-files` |

## Worktree Environment Bootstrap

新規 worktree は `.venv` を共有しない（空の環境から始まる）。`uv run` は default 依存と
`[dependency-groups] dev` は自動同期するが、**`[project.optional-dependencies] dev`
（pytest / black / mypy 本体）は `--extra dev` を明示しない限りインストールされない**。
そのため fresh worktree でいきなり `uv run pytest` / `ruff` / `black` / `mypy` を回すと
「command not found」で落ちる（Issue #534 Item 2）。

| 状況 | コマンド |
|------|---------|
| server の dev 依存を同期（テスト/lint の前に1度） | `uv sync --directory <path>/packages/garmin-mcp-server --extra dev` |
| web も触る場合 | `uv sync --directory <path>/packages/garmin-web`（+ frontend は `npm --prefix <path>/packages/garmin-web/frontend ci`） |

- **`scripts/ci-check.sh` は self-bootstrap する**（冒頭で上記 `uv sync` 等を実行）。
  ci-check.sh を回す経路（developer の完了ゲート / validation-agent の L2）では追加 sync 不要。
- 個別に `uv run pytest` 等を ci-check.sh より先に回す場合のみ、上表の sync を先に実行する。
