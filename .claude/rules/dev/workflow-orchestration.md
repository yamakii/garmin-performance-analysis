---
paths:
  - "packages/**"
  - ".claude/**"
  - "scripts/**"
  - "docker/**"
  - ".github/**"
  - "docs/**"
  - "CLAUDE.md"
---

# Workflow Orchestration

## Plan-First
- プランの要否と粒度は `implementation-workflow.md` Phase 0 の Tier 判定で決める: `design-approved` の Issue はそれ自体がプラン、リスク条件に当たる変更はフル（plan mode で承認）、それ以外は軽量プランを示して進む。手順数では判定しない
- If execution goes sideways: STOP and re-plan. Don't push through with workarounds.
- フルプランには検証手順（どう確かめるか）も含める

## Implementation
- プラン確定後は `implementation-workflow.md` Phase 1 のチェックリスト（そのセッションが worktree で実装 → PR → マージ）に従う
- 複数 Issue で `implementation-workflow.md` の起動条件（依存ティア 2 段以上、または依存の無い 4 件以上でファイル非共有）を満たすときは `/implement <epic>` を使う
- 変更ファイルの多い Issue（概ね 15 以上・ページ丸ごとの書き換え）は実装を `developer` サブエージェント（worktree 隔離）へ委譲し、メインセッションは照合・レビュー・Ship だけを行う（`implementation-workflow.md` Phase 1）。調査は Explore エージェントへ
- **全変更で Worktree → PR が必須**。Validation Level: skip は検証方法の指定であり、Worktree/PR 省略の許可ではない。skip レベルの docs/rules 変更で省略できるのは Issue だけ（`dev-reference.md` §1）
- 検証レベルと auto-merge ゲートは `worktree-validation-protocol.md` のみに書く。他所に再掲しない

## Self-Improvement Loop
- After ANY user correction: append to `.claude/tasks/lessons.md`
- Format: `- [YYYY-MM-DD] {mistake} -> {correct approach}`
- **lessons.md はルール昇格前の一時バッファ**（恒久ルールの正本ではない）。溜めっぱなしにせず定期的に triage する:
  再発防止をルール化できる教訓は `.claude/rules/` に昇格させ、一度きり・陳腐化したものは破棄する。
  棚卸しの手順は `/project-status` の Step 5 に組み込まれている
- lessons.md / settings.local.json は **git 管理外**。背景ジョブでは bg-isolation guard が shared checkout への
  Edit/Write を拒否するため、これらの追記・削除は **Bash 経由の `uv run python`** で行う（python 直叩き・Edit は不可）
- Write rules in `.claude/rules/` that prevent the same mistake from recurring
- セッション開始時: lessons.md を確認し、関連する過去の教訓を意識する

## Elegance Check
- If a fix feels hacky: step back and implement the elegant solution with full context.
- Simple fixes (typos, single-line, config): skip.

## Bug Fix Autonomy
- バグ報告と CI 失敗は確認を待たずに根本原因を調べ、修正・検証まで進めてよい（外部副作用は下の Autonomy Boundaries に従う）

## Autonomy Boundaries
- **外部副作用は毎回確認する**。PR マージの恒久承認（#886）はマージにしか及ばない。以下は別枠で、実行前にユーザーの確認を取る:
  - Garmin Connect への書き込み（`schedule_custom_workout` / `cleanup_generated_workouts(dry_run=False)` 等のカレンダー・ワークアウト変更）
  - cloud routine / scheduled agent / cron の作成・変更（`/schedule`, `/loop`, CronCreate）
  - GitHub リポジトリ設定の変更（branch protection, auto-merge, Dependabot, Actions 設定, secrets）
  - DB の削除・全件再生成（`--delete-db`, テーブル drop, `rm` を伴う data/ の操作）
- ユーザーの直接依頼がその操作自体であれば（例:「今日のロングランを Garmin に登録して」）、その **1 操作だけ**は依頼をもって承認済みとみなす。付随して発生する他の書き込み・削除・設定変更は都度確認する
- 背景ジョブ・非対話セッションでも同じ。確認が取れないなら、その操作を残して他を完了し、報告で `needs input:` として明示する
- 根拠: 2026-09-02 の保守セッションでユーザーが「定期ルーチン化以外は進めて」と明示的に切り分けた（cloud routine 作成は恒久承認の範囲外）

## Core Principles
1. Simplicity First: smallest change that solves the problem.
2. Root causes: 根本原因を直す。後回しにする `TODO` には Issue を切る。
3. Minimal Impact: unrelated cleanup goes in separate commit.
