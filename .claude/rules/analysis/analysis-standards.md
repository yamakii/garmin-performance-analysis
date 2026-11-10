# Analysis Standards

Consolidated reference for all analysis rules.

## 1. Data Access

- **MCP tools only**: `mcp__garmin-db__*` を使う。`duckdb.connect()` や `.duckdb` ファイルへの直接アクセスはしない。SQL を書くのは `export` の `query` 引数だけ
- **Token optimization**: `statistics_only=True` 優先 (67-80% 削減)。`get_splits_comprehensive()` で12フィールド一括取得
- **10+ activities**: Export workflow — PLAN(SQL設計) → EXPORT(parquet) → CODE(Python) → RESULT → INTERPRET
- **数値は当該テーブルから**: VO2max / LTHR / 体重 / HR ゾーン境界などの数値は、`athlete_profile.focus_notes` 等のプロフィール散文ではなく該当ツール（`get_vo2_max_data`、`get_lactate_threshold_data`、`get_body_composition_trend`、`get_heart_rate_zones_detail`）から取る。プロフィール記述は執筆時点のスナップショットで陳腐化する

## 2. Agent Rules

`/analyze-activity` が生成するセクションは **`run_note` の1つだけ**（run-note-analyst が担当）。数値・範囲判定・処方判定・シーン抽出は `get_run_report` が決定論的に算出済みで、run_note はそこに乗る散文（意味づけ・因果・流れ・重みづけ・次の一歩・再発と問い）のみを書く。共通ルール:

- **出力**: 日本語テキスト + English key names。`{ANALYSIS_TEMP_DIR}/{section_type}.json` に出力（ANALYSIS_TEMP_DIR は orchestrator が timestamp 付きユニークパスとして提供）。**事前の mkdir は不要**（Write tool が親ディレクトリを自動作成する）
- **JSON構造**: `{"activity_id": <int>, "activity_date": "<YYYY-MM-DD>", "section_type": "<type>", "analysis_data": {...}}`
- **HR zones**: Garmin native zones のみ (計算式禁止)
- **文体**: 自然な日本語（体言止め回避）、コーチ的トーン、具体的数値。ポイントごとに所見と根拠だけを簡潔に書く

- **Grounding**: run_note の主張には REPORT 上の evidence キー（`plan.<axis>` / `signals.<metric>` / `moments.<id>` / `recurrence.<kind>` / `vs_previous.<field>` / `conditions.<field>` / `context.<field>`）を必ず付ける。課題（growth point）にできるのは **outside かつ adverse なシグナル**、off-plan の軸、`policy.verdict == "concern"` のシーン（ランの目的から外れた逸脱）の3つだけで、範囲内・有利側のブレを弱点にしない

### Error Recovery

- `run_note` が登録された → 完了
- `run_note` が拒否された → merge の grounding ゲートが返した理由をそのままユーザーに報告する。自動リトライはしない

## 3. Coaching judgement（会話・スキル・run_note 共通）

**単一のランに成績はつけない**（星・点数・総合評価のいずれも出さない）。1本のランは REPORT の2つの問い（処方どおりだったか / いつもの自分と比べてどうか）で読む。ラン・プラン・相談への判断は次の4段で組み立てる:

1. **目的**: このラン・プランは何のためか。目的自身の基準で読み、その基準で達成できたことから始める
2. **事実**: データが示すことと、それが比較できるか（同じセンサー・同じ荷物・同じ基準。`comparability` / `provenance`）。主張はそれが決まる粒度で確かめ（ラン中の変化なら km ごと、平均で代えない）、ツールの注記（`reason`・参考値・`insufficient`）は数値と一緒に伝える。派生値をその入力の裏付けにしない
3. **適用条件**: ラベル（シーンの `kind` / `policy.verdict` / `flag_labels`）・ルール・過去の型（`retrospectives` / `focus_notes` の散文）を使う前に、その前提が今も成り立つかを `facts` や `export` の集計で確かめる。ラベルは入口であって結論ではなく、散文の言い換えは確認ではない
4. **確信度**: 高・中・低と、結論を変えうる条件を1つ添える

- **反論されたら**まず引用したデータを確かめ直し、データが変える部分だけを変える。丸ごと翻さず、根拠なく固執もしない
- **保守的なゲート**（カットバック・ACWR・症状・保護期間）は残すが、発動するときはこの走者に今それが当てはまる理由（ゲートの `reason_ja`）を添える
- **走者専用のルール**は `get_coaching_rules(scopes=[...])` で読む。リポジトリ（rules・skills・コード・Issue・PR）には書かない

### 改善提案

- 1本のランから出す提案は `next_challenge`＝**持ち越す1点**だけ（#1358）。今日の伸ばせる点（無ければ良かった点の維持）を1つ選んで行動の一文にし、その点の evidence を `next_challenge_evidence` に書く。次のセッションの中身（距離・ペース・心拍帯）は週の処方と `/daily-checkin` が決めるので、1本のランからは名指ししない
- 数値は処方の値の引用だけ（心拍上限はガード表現「150 bpm を超えないように」）。処方に無い帯やペースを作らない
- 一般的助言禁止（「もっと練習しましょう」→ このランの所見に根ざした具体的な行動にする）
- **持ち越す1点は維持目標であり今回の合否ではない**。目的を達したランには「成功条件」「失敗」の表現を使わず、「維持目標」「改善余地」として提示する（agent の prose・会話での引用の双方）
- **過敏な評価は閾値緩和ではなくカテゴリ分離で解く**: 「厳しすぎる」フィードバックの最初の一手は「一律に測っているものを training_type / 文脈で分けられないか」を問う（例: ペース CV はテンポ走はシビアに、LSD / 時間重視ロングは緩く）。既存の category 分離を確認し、閾値変更ではなく category 別の評価方針で分岐させる

## 4. Data Safety

- **data/ と result/ は git 未管理 — 削除したら復元不可能**
- 削除前: `ls -la` で中身確認 → ユーザーデータ有無判断 → ユーザー確認
- `rm -rf` をファイル有無未確認で実行禁止
- 誤配置ファイル → 正しいパスに移動してから削除

## 5. 過去の型を確かめるときの比較

- §3 の適用条件を確かめる比較は同じ基準で: 同じ暦期間か同じイベント前の同じ長さで並べ、基準を明示し、予定値は実績と分ける。週量平均だけでなく型が依存する条件（ロング本数・最長・直前の途切れ・レース後の伸び）を並べる
