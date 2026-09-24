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

# Implementation Workflow

プラン確定後のフロー（フルは承認後、軽量と設計済み Issue は提示後に進む。Phase 0）。各ステップの完了条件を満たさないと次に進めない。

## Phase 0: Plan Tier & Completeness Check

**本節がプランの要否と粒度の唯一の正本**。他のルール・skill は本節へリンクするだけにする。

### 0-1. 設計済み Issue はそれ自体がプラン

着手する Issue に `design-approved` が付いている（`/decompose` 由来を含む）なら、plan mode もプランの
書き直しもしない。`issue_read` で Design / Test Plan を読み、コードと突き合わせて前提が崩れていなければ
そのまま Phase 1 に進む。前提が崩れている（対象ファイル・シグネチャが消えた、Design と違う方針が要る）
ときだけ、下の Tier 判定に戻ってプランを作り直し、Issue を更新する。

### 0-2. Tier 判定

変更内容を以下と照合し、**1 つでも当たればフル、どれも当たらなければ軽量**。手順数やファイル数だけでは
フルにしない（3 ステップ以上はほぼ全変更に当たり、基準として機能しない）。

フル（plan mode でユーザー承認を取る）:
- 公開 Interface の追加・変更（MCP ToolDef の追加や引数変更、モジュールをまたいで呼ばれるクラス・関数のシグネチャ）
- DuckDB スキーマ変更・migration・ingest 時の導出変更（backfill を伴うもの）
- analyst agent 定義（L3）・`.claude/workflows/` ・`.claude/hooks/` の挙動変更
- 新しいパターン・依存ライブラリの導入、または `garmin-mcp-server` と `garmin-web` の両方にまたがる設計
- 方針の候補が複数あり選択がユーザーの判断に属する、または `[未検証]` の前提（Garmin API の値など）に依存する

軽量（plan mode 不要。プランを会話に示してそのまま Issue 作成 → Phase 1）:
- 上のどれにも当たらない変更。例: 根本原因が特定できたバグ修正、既存パターンに沿った reader / UI の修正、
  テスト追加、docs / rules / skills の改訂

実装中にフルの条件に当たると分かったら、そこで止めて plan mode でプランを出し直す。

### 0-3. 軽量プランの必須項目

- [ ] Issue: #{number} | TBD + Validation Level: L1|L2|L3|skip
- [ ] 目的（1〜2 行: 何を・なぜ）
- [ ] Files to Create/Modify — パスと new/modify
- [ ] Test Plan — test_{name} 形式と [unit|integration] マーカー、期待値を 1 行で（skip レベルは Verification の手順で代える）

Interface と Risks は書かない（書く必要が出たらフルの条件に当たっている）。Issue 本文もこの粒度でよい。

### 0-4. フルプランの必須項目

Phase 1 に進む前に、プランが以下を満たすことを確認。不足 → 補完してユーザーに再提示。

必須チェックリスト:
- [ ] Issue: #{number} | TBD + Validation Level: L1|L2|L3|skip
- [ ] Files to Create/Modify — パスと new/modify
- [ ] Interface — 新規クラス・関数の Python シグネチャ（既存変更のみの場合は変更メソッドのシグネチャ）
- [ ] Test Plan — test_{name} 形式、[unit|integration] マーカー、具体的入力値と期待値

thin plan の例（不足とみなす）:
- "Unit: パワーデータありのテスト" → test_xxx 形式でない、入力値なし
- Interface なしで新規クラス導入

例外: プロンプト変更のみ（.claude/agents/, .claude/rules/）→ Interface 省略可。Test Plan は必須。
※ これは Interface 省略の条件であり、Validation Level とは無関係（判定表は `worktree-validation-protocol.md` §1）。

Risks セクション（任意）:
- 計画時点で不確実な技術的判断・未検証の前提があれば記載する
- [検証済] / [未検証] タグで区別し、spike 推奨があればユーザーに判断を仰ぐ
- リスクなしなら省略可

## Phase 1: 既定経路 — 1 セッション = 1 worktree = 1 PR

承認済みの Issue は、**そのセッション自身が** worktree で実装し PR を作ってマージまで進める。
単発 Issue ではサブエージェントへの委任も Workflow も既定では使わない。複数 Issue は下の「`/implement` の起動条件」で
振り分ける。各ステップは 1 コマンド。

**実装だけを委譲する場合**: 変更ファイルが概ね 15 以上、またはページ / モジュール丸ごとの書き換えは、
そのセッションが `Agent(subagent_type="developer", isolation="worktree")` に**実装（下記 3〜4）を委譲**する。
メインセッションは Issue の Design / Test Plan との照合・diff レビュー・push（developer は push しない）・
PR 作成・CI 待ち・マージ・後片付け（下記 5〜11）だけを行い、実装や全ソース読み込みでコンテキストを消費しない。
委譲しても経路は同じ「1 セッション = 1 worktree = 1 PR」。
複数 Issue をまとめて流すかどうかは下の「`/implement` の起動条件」で決める。

1. **origin 同期**: ローカル main を `git.md` §2 の手順で同期。失敗したら報告して止まる（stash / reset はしない）
2. **worktree**: 背景ジョブは `EnterWorktree`、対話セッションは `git.md` §2 の `git worktree add`（パス・ブランチ名もそこ）
3. **実装 + テスト**: Issue の Design / Test Plan どおりに実装。`worktree-commands.md` の `--directory` / `-C` 形式でコマンドを打つ
4. **完了ゲート**: `packages/` を変えたら `uv run --directory <worktree> bash scripts/ci-check.sh` exit 0。`.claude/` `scripts/` `docker/` を変えたら `bash scripts/check-claude-scripts.sh` exit 0
5. **commit**: Conventional Commits、本文に `Closes #<issue>`、ハーネス指定の attribution trailer
6. **push**: `git.md` §2 の正典形。origin/main の事前取り込みはしない
7. **PR**: `mcp__github__create_pull_request`（body: `Closes #<issue>` + `## Verification` に実行した検証コマンドと結果）
8. **CI 待ち**: `bash scripts/wait-for-ci.sh <PR> --timeout 900`（メインセッションは `run_in_background` 可。サブエージェント内ならフォアグラウンド 1 回）
9. **マージ**: `worktree-validation-protocol.md` §6 のゲートを満たせば `mcp__github__merge_pull_request(merge_method="merge")`。コンフリクトは `git.md` §2 で解消して 8 から。その他の例外（検証 FAIL / WARNING / CI 失敗）は PR URL と理由を報告して止まる
10. **後片付け**: ローカル main 同期（`git.md` §2）→ `bash scripts/cleanup-merged-worktrees.sh`。MCP サーバコードを変えたら `mcp__garmin-db__reload_server()`。
    **背景ジョブ（`EnterWorktree` 中）でも必ず実行する**: worktree セッションの Bash guard は他 checkout への git 操作を拒むので、
    最後の PR をマージしたら `ExitWorktree(action="remove")`（未マージの変更が無いことが条件）で `/workspace` に戻り、
    そこで上の 2 コマンドを実行する。「worktree からは同期できない」と報告して人に回すのは禁止（オーナー指摘 2026-09-08）
11. **報告**: PR 番号、マージ SHA、実行した検証、未了の追跡義務（L3 の post-merge E2E など）

複数 Issue を続けて扱うときは Issue ごとに 2〜11 を繰り返す。同じ worktree で次のブランチを切るなら
`git.md` §2「同じ worktree で 2 本目」（前の PR がマージ済みの場合）。

### `/implement` の起動条件

作業が Epic 配下の複数 Issue（各 Issue に Design + Files to Create/Modify + Test Plan）に分かれ、次の
**どちらか**を満たすなら `/implement <epic>` を使う。`implement-tier` Workflow が developer / validation-agent を
並列に回し、同じゲートで auto-merge する。

- **(a) 依存ティアが 2 段以上**: `Blocked by` の連鎖がある（#1115: 3 ティア Epic をメインセッションで直列実装し、
  コストとコンテキストを逼迫させた再発防止）
- **(b) 依存の無い Issue が 4 件以上**で、**同じティアの Issue 同士の Files to Create/Modify が 1 つも重ならない**

どちらにも当たらない単発 Issue・依存の無い 2〜3 件は既定経路（上記）で直列に処理する方が速く、失敗の型も少ない。

判断の前提:
- **利点は並列による所要時間の短縮とメインのコンテキスト保護で、トークン節約ではない**。実装担当の `developer` は
  opus で、Issue ごとに developer / validation / ship / merge の 4 エージェントがコールドスタートでルールとコードを
  読み直し、escalate された PR はメインが処理する。コンテキスト保護だけが目的なら上の developer 委譲で足りる
- **条件を満たすために Issue を細かく割らない・偽の `Blocked by` を作らない**。PR 数とコールドスタートが増えるだけ
- **同じティアのファイル重複はコンフリクトの主因**（兄弟マージ後に必ず conflict で escalate する）。(a) でも同じ
  ティアに重なりがあれば、後の Issue に `Blocked by` を付けて次ティアへ送る。`/decompose` の段階でファイル所有で
  切っておくと両条件を満たしやすい

## Phase 2: Verify

マージ前に:

- サブエージェントに委任した場合は、diff を Issue の Files / Interface / Test Plan と照合する（テスト名が全て存在するか）
- Validation Level ごとの手順・完了条件は `worktree-validation-protocol.md` §1〜§5
- マージ判定の根拠は報告文ではなく `pull_request_read` の check-runs と mergeable

## Phase 3: Ship

手順・auto-merge ゲート・例外・恒久承認（#886）の範囲は `worktree-validation-protocol.md` §6 が正本。
既定経路では Phase 1 の 6〜10 がそれに当たる。`/implement` 経由では Workflow が同じゲートを内包する。
