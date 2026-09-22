---
paths:
  - "packages/**"
  - ".claude/**"
  - "scripts/**"
  - "docker/**"
  - ".github/**"
  - "docs/**"
---

# Git

**本書が git 運用の唯一の正本**（#1304 でゼロベース再設計）。他のルール・skill・workflow は
ここへリンクするだけにし、コマンドを再掲しない。各原則の「理由」が崩れたら原則ごと見直す。

## 1. 原則

| 原則 | 理由 | 強制 |
|------|------|------|
| main は PR のマージでしか変わらない | branch protection が PR を要求し、`ci-guard` が唯一のゲート | `block-commit-on-main.sh` / `guard-push.sh` |
| **push 済みの履歴は書き換えない**（force push・push 済み commit の rebase / amend / reset をしない） | CI 実行・PR レビュー・他 worktree の参照が壊れる。コンフリクトは merge commit で 1 回解けば済み、書き換えの利得がない | `guard-push.sh`（`--force` / `-f`） |
| 未 push のローカル commit は自由に整理してよい（amend 等） | 誰も参照していない | — |
| PR は merge commit でマージ（`merge_method="merge"`） | `cleanup-merged-worktrees.sh` / `prune-merged-branches.sh` が ancestry（`--merged` / `merge-base --is-ancestor`）でマージ済みを判定する。squash だと全ブランチが「未マージ」で残る | Dependabot workflow も `--merge` |
| feature ブランチへの origin/main 取り込みは**コンフリクト時だけ** | branch protection は up-to-date を要求せず、CI は PR の merge ref を検証する。遅れているだけの PR はそのままマージできる | — |
| stash を使わない（一時退避は WIP commit） | stash スタックは全 worktree・並行セッションで共有され、他人の退避を pop しうる | — |
| **出力は必要な分だけ取る**（§3） | git 出力はそのままコンテキストに載る。無制限の `log` / `diff` / `show` と、diffstat を吐く `merge` が主な浪費源だった（#1304 の計測: 同期系 431 回で約 19.5 万字） | リポジトリ設定 `merge.stat=false`（SessionStart hook `git-quiet-config.sh` が毎回設定、#1307）。フラグを忘れても、開始時に旧ルールを掴んだセッションでも merge / pull は diffstat を出さない。`--no-stat` は念のための二重化 |

## 2. 正典コマンド

worktree セッションではハーネスの静的ガードにより **1 Bash コマンドに git は 1 回**、`cd` せず
`git -C <path>`。

| 場面 | コマンド |
|------|---------|
| ローカル main を origin に同期 | `git fetch -q origin main` → `git merge -q --no-stat --ff-only origin/main`。失敗したら報告して止まる（stash / reset しない） |
| worktree 作成 | 背景ジョブ: `EnterWorktree`。対話: `git worktree add -q -b <type>/<issue>-<slug> .claude/worktrees/<slug> origin/main`（`type` = feat / fix / docs / chore） |
| 同じ worktree で 2 本目 | `git fetch -q origin main` → `git checkout -q -b <branch> origin/main` |
| commit | Conventional Commits、単一関心、本文に `Closes #<issue>`、ハーネス指定の attribution trailer。`--no-verify` / `-n` は `guard-no-verify.sh` が止める |
| push | `git -C <wt> -c credential.helper='!f(){ echo username=x-access-token; echo password=$GITHUB_TOKEN; };f' push -q -u origin <branch>`（`implement-tier.js` の `pushCmd` が正典） |
| コンフリクト解消（PR が `mergeable=false` のときだけ） | `git -C <wt> fetch -q origin main` → `git -C <wt> merge -q --no-stat --no-edit origin/main` → 衝突ファイルは `git -C <wt> diff --name-only --diff-filter=U` で列挙して解消 → commit → 通常 push。解けないときは `git -C <wt> merge --abort` して報告 |
| マージが「not up to date」で拒否されたとき | `mcp__github__update_pull_request_branch`（GitHub 側で merge、ローカル出力なし）→ CI 待ち → 再マージ |
| マージ後 | 上の「ローカル main 同期」→ `bash scripts/cleanup-merged-worktrees.sh`。worktree は `--force` なしで remove、ブランチは `-d`（`-D` 禁止） |

## 3. 読み出しの予算

| 用途 | こう取る | 取らない |
|------|---------|---------|
| 履歴 | `git log --oneline -n 10`、範囲は `git log --oneline A..B` | 件数上限なしの `git log` / `-p` |
| 差分の当たり | `git diff --shortstat A...B`、`git diff --stat A...B \| tail -n 20` | いきなり全体 `git diff` |
| 差分の中身 | `git diff A...B -- <file>`（ファイル単位） | 複数ファイルを一括 |
| 過去版のファイル | `git show <ref>:<path> \| sed -n 'a,bp'`、現行版なら Read | `git show <ref>:<path>` 全文 |
| commit の概要 | `git show --stat --oneline <sha>` | `git show <sha>`（patch 全文） |
| 状態 | `git status --short` | `git status` |
| 同期・書き込み | `fetch` / `merge` / `checkout` / `push` に `-q`、`merge` に `--no-stat` | 進捗・diffstat・ref 一覧の垂れ流し |

PR の差分レビューはローカル diff より `pull_request_read(method="get_files")` でファイル一覧 → 必要な
ファイルだけ diff を見る。
