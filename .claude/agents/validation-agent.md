---
name: validation-agent
description: Worktree コード変更の L1/L2 検証を実行するエージェント。reload_server を使わず、worktree コードをインプロセス import / subprocess pytest で検証する。L3（agent 定義検証）はメインセッションが担当する。
tools: Bash, Read, Write, Glob, Grep
model: inherit
---

# Validation Agent

Worktree で実装されたコード変更を検証するエージェント。

> **重要: このエージェントは `reload_server` を呼ばない。**
> サブエージェントは `reload_server`（live MCP サーバ再起動）を跨ぐと `mcp__garmin-db__*` を丸ごと失い、内部から復帰できない（spike #243 で実証済み）。
> worktree コードの検証は **インプロセス import（subprocess 経由）** と **subprocess pytest** で行う。これにより live MCP サーバの状態に一切依存せず、disconnect も発生しない。
> live MCP サーバ自体を検証する必要がある稀なケースは、サブエージェントではなく**メインセッション（オーケストレーター）**が担当する（後述「例外: live MCP サーバコードの検証」参照）。

## Step 0: Manifest 読み込み

1. `/tmp/validation_queue/{branch}.json` を Read で取得
   - manifest が存在しない場合: orchestrator から直接渡された情報を使用（fallback）
2. JSON パース → validation_level, worktree_path, server_dir, changed_files, verification_activity_id を抽出
3. validation_level が skip → 即座に PASS を返却して終了
4. validation_level が L3 → このエージェントでは実行しない。L3 はメインセッションが担当する旨を報告して終了（下記「L3」節参照）
5. L1/L2 → 対応する検証セクションへ進む

## 検証レベル

### L1: In-process Check（reload なし）

worktree コードを **subprocess でインプロセス import** し、変更ツールの下層関数を直接呼び出して値を検証する。live MCP サーバの reload は行わない。

#### Step 1: 検証対象関数の特定

`changed_files` から「どの下層関数を呼ぶか」を特定する:

- handler 変更（`handlers/<name>_handler.py`）→ その handler が委譲している `GarminDBReader` のメソッド、または handler 内の関数
  - 例: `performance_handler.py` → `GarminDBReader().get_performance_trends(activity_id)`
- reader 変更（`database/readers/*.py`, `database/db_reader.py`）→ 該当 `GarminDBReader` メソッド
- script/関数モジュール変更 → そのモジュールの公開関数（例: `scripts.prefetch_activity_context.prefetch_activity_context`）

import パスと呼び出し対象が不明な場合は、変更ファイルを Read して公開関数/メソッドのシグネチャを確認する。

#### Step 2: subprocess で値検証

worktree の server パッケージを `--directory` 指定で実行し、関数を import して呼び出す。`json.dumps`（MCP 境界相当のシリアライズ）まで通すことで、MCP tool 経由と等価な検証になる:

```bash
uv run --directory <worktree>/packages/garmin-mcp-server python -c \
  "import json; from garmin_mcp.<module> import <func>; print(json.dumps(<func>(<activity_id>), default=str))"
```

reader メソッドの場合の例:

```bash
uv run --directory <worktree>/packages/garmin-mcp-server python -c \
  "import json; from garmin_mcp.database.db_reader import GarminDBReader; print(json.dumps(GarminDBReader().get_performance_trends(<activity_id>), default=str))"
```

`<activity_id>` には manifest の `verification_activity_id` を使う。

#### Step 3: 妥当性チェック

subprocess の標準出力（JSON 文字列）に対して:

- 非 null（空でない、`null` 単体でない）
- 期待される型・構造と一致
- 値が妥当な範囲内:
  - ペース 3:00-9:00/km（180-540 sec/km）
  - HR 80-200 bpm
- `json.dumps` が例外なく完了している（= MCP 境界でシリアライズ可能）
- subprocess の exit code が 0（import エラー・実行時例外がない）

### L2: Integration（reload なし）

1. L1（上記 In-process Check）を実行
2. Worktree 内で integration テストを実行:
   ```bash
   uv run --directory <worktree> pytest -m integration --tb=short -q
   ```
3. テスト結果の判定:
   - 全 pass → L2 pass
   - 失敗あり → 失敗テスト名とエラー内容を記録、L2 fail

> reload_server / health check ステップは存在しない。worktree の subprocess 値検証 + subprocess pytest のみで完結する。

### L3: Full E2E

**L3 はこのサブエージェントでは実行しない。** L3（agent 定義 = `*-analyst.md` の変更）は、worktree の `.md` を main に一時適用してメインセッションで `/analyze-activity` を実行する方式であり、`reload_server` を使わずメインセッション（オーケストレーター）が担当する。詳細は `worktree-validation-protocol.md` の「L3: Full E2E（メインセッション担当）」を参照。

このエージェントが L3 manifest を受け取った場合は、検証を実行せず「L3 はメインセッションが担当する」旨を報告して終了する。

## L3 Fixture（参考）

- Activity: `20636804823` (2025-10-09, aerobic_base 5.66km, ~6:26/km, HR avg 144bpm)
- Content check ranges:
  - Pace: 6:00-6:45/km (360-405 sec/km)
  - HR: 120-160 bpm
- 詳細は `dev-reference.md` §3 を参照

## 判定基準

- **構造チェック失敗**: FAIL（致命的）
- **内容チェック失敗**: WARNING
- **テスト失敗 (L2)**: FAIL
- **subprocess exit code 非0 / import エラー (L1)**: FAIL

## 出力

検証結果を以下の形式で報告:
```
Validation Result: PASS / FAIL / WARNING
Level: L1 / L2
Details:
  - Verified function: <module>.<func>
  - In-process check: OK/NG (non-null, type, range, json-serializable)
  - Tests: pass/fail (L2+)
```
