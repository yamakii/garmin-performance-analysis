---
paths:
  - "packages/garmin-mcp-server/src/garmin_mcp/validation/**"
  - "packages/garmin-mcp-server/src/garmin_mcp/analysis/**"
  - ".claude/agents/**"
  - ".claude/skills/**"
  - ".claude/rules/**"
  - ".claude/workflows/**"
  - ".claude/hillclimb/**"
---

# コーチ出力の誤りへの対処（Epic #1544）

run_note・会話・スキルのコーチ出力に誤りが見つかっても、LLM が読む文章（`contracts.py` の契約、
`.claude/agents/`、skills、rules、memory）に**「この場面ではこう書け／こう書くな」を足さない**。
場面別の指示は原則より優先されて境界の外で次の誤りを生み、写しと矛盾を増やす（#1517 → #1542）。
REPORT の事実と食い違う散文も例外ではない。

1. **評価ケースにする**: 誤りは `.claude/hillclimb/coach-review/cases.local.json`（git 管理外。走者固有の
   内容はここだけ）にケースとして足す。正解が分かれる対の事例があれば対で足す。期待値は結論の文言ではなく、
   原則で判断できているか（何と何を比べたか、目的の基準で読んだか）で書く。ケースは誤りの記録も兼ねるので
   `logged`（記録日）・`source`（`owner` = オーナーの訂正 / `self` / `eval`）・`triage`（下の分類）と、
   同種の誤りが前にあれば `recurs_of`（そのケース id）を埋める
2. **分類する**:
   - 計算できる事実・判定の誤り → run report / merge ゲートの**コード**を直す
   - 原則の適用ミス → 原則の書き方か手本を見直す（場面の言い方は足さない）
   - 原則そのものの欠落 → 原則として足す（まれ）。足すなら同じだけ統合か削除と対にする
   - 許容できるばらつき → 記録だけ
3. **評価セットで確かめる**: LLM が読む文章の変更は評価セットで測ってからマージする。1 本のランの再分析で
   直ったと判断しない。測る範囲は影響する種類に絞る（Max 使用量のため）:
   - 文章を変えない変更（判断をコードへ移す・テスト・ハーネス）→ 単体テストのみ、評価は回さない
   - 契約・agent 定義 → `run_note` ケースだけ。rules・skills・memory → `conversation` ケースだけ
   - 同じ層の文章変更が続くときはまとめて 1 回測り、退行したら `--only` でそのケースを切り分ける
   - 種類全体の前に、対の事例と前回落ちたケースで当たりを見る。段階や大きな整理の終わりに全件 1 回
   - 1 回の実行の差を効果とみなさない（部分評価 1 回で O2 +0.4 に見えた改善が全件では再現しなかった）。
     採否を決める比較は差の出たケースを `--reps 2` で確かめる
4. **総量の予算を守り、指標を残す**:
   - 契約・run-note-analyst・コーチ系 skills・常時読み込みのルールは層ごとにバイト上限がある
     （`.claude/rule-budget.json`、`tests/docs/test_rule_budget.py` が CI で検査）。超えたら足した分だけ統合か
     削除する。削って余裕が 2 KB を超えたら `rule_budget --write` で上限も下げる（上限は下がる方向にしか動かない）
   - 上限を上げてよいのは分類が「原則の欠落」で、評価で測り、PR でオーナーが承認したときだけ
   - 1 件処理したら `node .claude/hillclimb/coach-review/indicators.mjs` と
     `uv run --directory packages/garmin-mcp-server python -m garmin_mcp.scripts.rule_budget --history` の
     出力を Issue / PR に貼る。これが訂正頻度・再発率・総量推移の記録になる（別の保存先は作らない）
