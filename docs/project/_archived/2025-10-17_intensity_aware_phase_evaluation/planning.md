# 計画: Intensity-Aware Phase Evaluation

## プロジェクト情報
- **プロジェクト名**: `intensity_aware_phase_evaluation`
- **作成日**: `2025-10-17`
- **ステータス**: 計画中
- **関連Issue**: (作成後にリンクを追加)

## 要件定義

### 目的

トレーニングタイプ（`hr_efficiency.training_type`）に基づいてフェーズ評価ロジックとレポート出力を適応させ、低～中強度走で不適切な警告が出るのを防ぐ。

### 解決する問題

**現状の問題:**
- phase-section-analystは全てのランニングで3フェーズ（warmup/run/cooldown）または4フェーズ（warmup/run/recovery/cooldown）を想定
- 低～中強度走（リカバリー、ベースラン）では：
  - ウォームアップなしで始まることが一般的
  - クールダウンなしで終わることが一般的
  - 全体が1つのメインフェーズのみで構成される
- 現在の実装では、これらのケースで不適切な警告（「ウォームアップがないため怪我リスクが高まる」等）を出している
- レポート出力も一律同じで、トレーニングタイプに応じた表現になっていない

**影響:**
- ユーザーが低強度走でも「ウォームアップ不足」の警告を受け取る
- フェーズ評価の信頼性が低下
- トレーニングタイプに応じた適切なフィードバックができない
- レポート出力が画一的で、トレーニング目的に沿わない

### ユースケース

**トレーニングタイプ分類（hr_efficiency.training_typeを使用）:**

1. **低～中強度走カテゴリ**
   - **training_type**: `recovery`, `aerobic_base`
   - **フェーズ要件**: ウォームアップ・クールダウン**不要**
   - **フェーズ評価例**:
     - ウォームアップなし: "リカバリー走のため、ウォームアップなしでも問題ありません"
     - クールダウンなし: "低強度走のため、クールダウンなしでも問題ありません"
   - **レポート出力**: 警告なし、リラックスしたトーンで評価

2. **テンポ・閾値カテゴリ**
   - **training_type**: `tempo`, `lactate_threshold`
   - **フェーズ要件**: ウォームアップ・クールダウン**推奨**（なければ軽い注意）
   - **フェーズ評価例**:
     - ウォームアップなし: "テンポ走では軽いウォームアップが推奨されます"
     - クールダウンなし: "クールダウンがあるとより良いでしょう"
   - **レポート出力**: 推奨レベルの注意、改善提案のトーン

3. **インターバル・スプリントカテゴリ**
   - **training_type**: `vo2max`, `anaerobic_capacity`, `speed`
   - **フェーズ要件**: ウォームアップ・クールダウン**必須**（なければ警告）
   - **フェーズ評価例**:
     - ウォームアップなし: "高強度走ではウォームアップが必須です。怪我リスクが高まります"
     - クールダウンなし: "高強度走後はクールダウンが重要です。疲労回復が遅れる可能性があります"
   - **レポート出力**: 明確な警告、安全性重視のトーン

4. **4フェーズ構造（インターバルトレーニング）**
   - **判定基準**: recovery_splitsが存在する場合
   - **扱い**: 常にインターバル・スプリントカテゴリ（既存ロジック維持）
   - **レポート出力**: インターバル特有の詳細評価

---

## 設計

### アーキテクチャ

```
User Request
    ↓
phase-section-analyst (updated)
    ↓
1. Training Type Determination (NEW)
   - Input: hr_efficiency.training_type
   - Output: training_category ("low_moderate", "tempo_threshold", "interval_sprint")
    ↓
2. Phase Structure Detection (existing)
   - Input: performance_trends.recovery_splits
   - Output: phase_count (3 or 4)
   - Note: 4フェーズの場合は常に"interval_sprint"扱い
    ↓
3. Phase Evaluation with Training Type Context (updated)
   - Input: training_category, phase_data
   - Output: context-aware evaluation text
    ↓
4. Insert to DuckDB (existing)
   - section_type: "phase"
   - analysis_data: {warmup_evaluation, run_evaluation, [recovery_evaluation], cooldown_evaluation}
    ↓
5. Report Generation with Training Type Context (NEW)
   - Input: training_category, phase evaluation
   - Output: Training type-aware report text (tone, severity, recommendations)
```

**変更箇所:**
- `.claude/agents/phase-section-analyst.md` - トレーニングタイプ判定と評価ガイドライン更新
- `tools/reporting/templates/detailed_report.j2` - フェーズ評価セクションのトーン調整（オプション）
- DuckDBスキーマは変更なし
- 他のエージェント（split/summary/efficiency/environment）には影響なし

### データモデル

**既存のDuckDBスキーマ（変更なし）:**

```sql
-- hr_efficiency テーブル (トレーニングタイプ取得に使用)
CREATE TABLE hr_efficiency (
    activity_id BIGINT PRIMARY KEY,
    training_type VARCHAR,                    -- カテゴリ判定に使用
    zone1_percentage DOUBLE,
    zone2_percentage DOUBLE,
    zone3_percentage DOUBLE,
    zone4_percentage DOUBLE,
    zone5_percentage DOUBLE,
    -- ... other fields
);

-- performance_trends テーブル (フェーズデータ取得に使用)
CREATE TABLE performance_trends (
    activity_id BIGINT PRIMARY KEY,
    warmup_splits VARCHAR,                    -- JSON array
    main_splits VARCHAR,                      -- JSON array
    recovery_splits VARCHAR,                  -- JSON array (4フェーズ判定)
    finish_splits VARCHAR,                    -- JSON array
    -- ... other fields
);

-- section_analyses テーブル (変更なし)
CREATE TABLE section_analyses (
    activity_id BIGINT,
    activity_date DATE,
    section_type VARCHAR,
    analysis_data JSON,
    metadata JSON,
    PRIMARY KEY (activity_id, section_type)
);
```

**トレーニングタイプカテゴリマッピング（agent prompt内で定義）:**

```python
# Training Type Category Mapping
training_type_categories = {
    "low_moderate": {
        "types": ["recovery", "aerobic_base"],
        "warmup_required": False,
        "cooldown_required": False,
        "warning_level": "none",
        "tone": "relaxed"
    },
    "tempo_threshold": {
        "types": ["tempo", "lactate_threshold"],
        "warmup_required": "recommended",
        "cooldown_required": "recommended",
        "warning_level": "light",
        "tone": "suggestive"
    },
    "interval_sprint": {
        "types": ["vo2max", "anaerobic_capacity", "speed"],
        "warmup_required": True,
        "cooldown_required": True,
        "warning_level": "strong",
        "tone": "assertive"
    }
}
```

### API/インターフェース設計

**使用MCPツール:**

```python
# phase-section-analyst で使用
mcp__garmin_db__get_hr_efficiency_analysis(activity_id: int) -> dict
  # Returns: {..., "training_type": "recovery" | "aerobic_base" | "tempo" | etc.}

mcp__garmin_db__get_performance_trends(activity_id: int) -> dict
  # Returns: {..., "warmup_splits": [...], "recovery_splits": [...], ...}

mcp__garmin_db__insert_section_analysis_dict(
    activity_id: int,
    activity_date: str,
    section_type: str,
    analysis_data: dict
)
```

**更新されるエージェントプロンプト構造:**

```markdown
# Phase Section Analyst (Updated)

## 新機能: トレーニングタイプ判定ロジック

**実行手順:**
1. `get_hr_efficiency_analysis(activity_id)`で`training_type`を取得
2. トレーニングタイプカテゴリにマッピング:
   - **低～中強度**: `recovery`, `aerobic_base` → フェーズ不要
   - **テンポ・閾値**: `tempo`, `lactate_threshold` → フェーズ推奨
   - **インターバル・スプリント**: `vo2max`, `anaerobic_capacity`, `speed` → フェーズ必須
3. `get_performance_trends(activity_id)`でフェーズ構造を確認
4. カテゴリに応じたフェーズ評価を実施

## 評価ガイドライン（トレーニングタイプ別）

### 低～中強度走 (recovery, aerobic_base)
- **トーン**: リラックス、肯定的
- **ウォームアップ評価**:
  - 存在する: 「リカバリー走ではオプショナルですが、丁寧な準備ができています」
  - 存在しない: 「低強度走のため、ウォームアップなしでも問題ありません」（★★★★★ 警告なし）
- **クールダウン評価**:
  - 存在する: 「丁寧なクールダウンで身体をケアできています」
  - 存在しない: 「低強度走のため、クールダウンなしでも問題ありません」（★★★★★ 警告なし）

### テンポ・閾値走 (tempo, lactate_threshold)
- **トーン**: 改善提案、教育的
- **ウォームアップ評価**:
  - 存在する: 「テンポ走に適したウォームアップができています」（★★★★★）
  - 存在しない: 「テンポ走では軽いウォームアップが推奨されます（★★★☆☆ 推奨）
- **クールダウン評価**:
  - 存在する: 「適切なクールダウンができています」（★★★★★）
  - 存在しない: 「クールダウンがあると疲労回復がより効果的になります」（★★★☆☆ 推奨）

### インターバル・スプリント (vo2max, anaerobic_capacity, speed)
- **トーン**: 安全重視、明確な指示
- **ウォームアップ評価**:
  - 存在する: 「高強度トレーニングに必要なウォームアップができています」（詳細評価）
  - 存在しない: 「⚠️ 高強度走ではウォームアップが必須です。怪我リスクが高まります」（★☆☆☆☆ 警告）
- **クールダウン評価**:
  - 存在する: 「高強度後の適切なクールダウンができています」（詳細評価）
  - 存在しない: 「⚠️ 高強度走後はクールダウンが重要です。疲労回復が遅れる可能性があります」（★☆☆☆☆ 警告）
```

---

## 実装フェーズ

### Phase 1: エージェントプロンプト更新

**実装順序: TDD cycle (Red → Green → Refactor)**

#### 1.1 トレーニングタイプ判定ロジック追加
- **Test**: カテゴリマッピングのテスト（7種類のtraining_type → 3カテゴリ）
- **Implementation**: `.claude/agents/phase-section-analyst.md` にカテゴリマッピングセクション追加
- **Refactor**: マッピングロジックの明確化、未知のtraining_typeの処理

#### 1.2 フェーズ評価ガイドライン更新
- **Test**: カテゴリ別フェーズ評価のテスト（ウォームアップあり/なし × 3カテゴリ = 6パターン）
- **Implementation**: 評価ガイドラインにカテゴリ別の記述を追加
- **Refactor**: 評価テキストのトーン統一（relaxed/suggestive/assertive）

#### 1.3 レポート出力の調整（オプション）
- **Test**: トレーニングタイプ別のレポート出力テスト
- **Implementation**: `tools/reporting/templates/detailed_report.j2` のフェーズセクション更新（必要に応じて）
- **Refactor**: 後方互換性の確保（既存レポートも表示可能）

### Phase 2: 実データでの検証

**実装順序: 実データテスト → 調整 → 最終確認**

#### 2.1 低強度走でのテスト
- **Test**: ジョグ（平均ペース > 5:30/km）でフェーズなしのケース
- **Expected**: ウォームアップ・クールダウンなしでも警告が出ない
- **Validation**: 評価テキストに「低強度走のため」の記述がある

#### 2.2 中強度走でのテスト
- **Test**: テンポ走（平均ペース 4:30-5:30/km）でフェーズありのケース
- **Expected**: ウォームアップ・クールダウンあり → 推奨メッセージ、なし → 軽い注意
- **Validation**: 評価テキストに「推奨」または「軽い注意」の記述がある

#### 2.3 高強度走でのテスト
- **Test**: インターバル（平均ペース < 4:30/km）でフェーズありのケース
- **Expected**: ウォームアップ・クールダウンあり → 詳細評価、なし → 警告
- **Validation**: 評価テキストに「必須」または「警告」の記述がある

#### 2.4 インターバルトレーニング（4フェーズ）でのテスト
- **Test**: recovery_splitsが存在するケース
- **Expected**: 常に高強度扱い、既存の評価ロジック維持
- **Validation**: recovery_evaluationが含まれる

### Phase 3: ドキュメント更新

#### 3.1 エージェント定義更新
- `.claude/agents/phase-section-analyst.md` に強度判定セクション追加
- 評価ガイドラインを強度別に整理

#### 3.2 CLAUDE.md 更新
- "Agent System" セクションに強度判定機能の記述追加

#### 3.3 completion_report.md 作成
- 実装完了後、テスト結果と評価を記録

---

## テスト計画

### Unit Tests

**テストファイル**: `tests/agents/test_phase_section_analyst_intensity.py`

#### 強度判定ロジックテスト (6テスト)

1. **Easy/Recovery 判定**
   - [ ] `test_intensity_easy_by_pace()` - avg_pace > 330 sec/km → "easy"
   - [ ] `test_intensity_easy_by_hr()` - avg_hr < 70% → "easy"

2. **Moderate 判定**
   - [ ] `test_intensity_moderate_by_pace()` - avg_pace 270-330 sec/km → "moderate"
   - [ ] `test_intensity_moderate_by_hr()` - avg_hr 70-85% → "moderate"

3. **High 判定**
   - [ ] `test_intensity_high_by_pace()` - avg_pace < 270 sec/km → "high"
   - [ ] `test_intensity_high_by_hr()` - avg_hr > 85% → "high"

#### フェーズ評価テスト (12テスト)

1. **Easy/Recovery フェーズ評価**
   - [ ] `test_easy_with_warmup()` - ウォームアップあり → 「オプショナルですが適切」
   - [ ] `test_easy_without_warmup()` - ウォームアップなし → 「問題ありません」（警告なし）
   - [ ] `test_easy_with_cooldown()` - クールダウンあり → 「丁寧なクールダウン」
   - [ ] `test_easy_without_cooldown()` - クールダウンなし → 「問題ありません」（警告なし）

2. **Moderate フェーズ評価**
   - [ ] `test_moderate_with_warmup()` - ウォームアップあり → 「適したウォームアップ」
   - [ ] `test_moderate_without_warmup()` - ウォームアップなし → 「推奨されます」（軽い注意）
   - [ ] `test_moderate_with_cooldown()` - クールダウンあり → 「適切なクールダウン」
   - [ ] `test_moderate_without_cooldown()` - クールダウンなし → 「あるとより良い」（軽い注意）

3. **High フェーズ評価**
   - [ ] `test_high_with_warmup()` - ウォームアップあり → 「必要なウォームアップ」（詳細評価）
   - [ ] `test_high_without_warmup()` - ウォームアップなし → 「必須です。怪我リスク」（警告）
   - [ ] `test_high_with_cooldown()` - クールダウンあり → 「適切なクールダウン」（詳細評価）
   - [ ] `test_high_without_cooldown()` - クールダウンなし → 「重要です。疲労回復」（警告）

### Integration Tests

**テストファイル**: `tests/integration/test_phase_analyst_intensity_integration.py`

1. **実データテスト (3ケース)**
   - [ ] `test_real_data_easy_run()` - 実際の低強度走データで検証
   - [ ] `test_real_data_moderate_run()` - 実際の中強度走データで検証
   - [ ] `test_real_data_high_run()` - 実際の高強度走データで検証

2. **DuckDB統合テスト (2ケース)**
   - [ ] `test_insert_section_analysis_with_intensity_context()` - 強度コンテキスト付きでDuckDBに保存
   - [ ] `test_backward_compatibility()` - 既存のレポート生成が正常に動作

3. **エージェント実行テスト (3ケース)**
   - [ ] `test_agent_execution_easy()` - エージェント実行で低強度走を正しく評価
   - [ ] `test_agent_execution_moderate()` - エージェント実行で中強度走を正しく評価
   - [ ] `test_agent_execution_high()` - エージェント実行で高強度走を正しく評価

### Performance Tests

**テストファイル**: `tests/performance/test_phase_analyst_performance.py`

1. **処理時間測定**
   - [ ] `test_intensity_determination_performance()` - 強度判定処理時間 < 10ms
   - [ ] `test_phase_evaluation_performance()` - フェーズ評価処理時間 < 100ms

2. **トークン効率測定**
   - [ ] `test_token_efficiency_comparison()` - 更新前後のトークン消費量比較
   - [ ] 目標: トークン消費量は同等または削減（強度コンテキスト追加による増加を最小化）

---

## 受け入れ基準

### 機能要件
- [ ] phase-section-analystがhr_efficiency.training_typeから判定を実行できる
- [ ] 低～中強度走（recovery, aerobic_base）でフェーズなしでも警告が出ない
- [ ] テンポ・閾値走（tempo, lactate_threshold）でフェーズがない場合、推奨レベルの注意が出る
- [ ] インターバル・スプリント（vo2max, anaerobic_capacity, speed）でフェーズがない場合、明確な警告が出る
- [ ] インターバルトレーニング（4フェーズ）の既存評価ロジックが維持されている
- [ ] section_analysesテーブルにトレーニングタイプコンテキストが保存される
- [ ] レポート出力がトレーニングタイプに応じたトーン（relaxed/suggestive/assertive）で表示される

### テスト要件
- [ ] 全Unit Testsがパスする（18テスト）
- [ ] 全Integration Testsがパスする（8テスト）
- [ ] 全Performance Testsがパスする（2テスト）
- [ ] テストカバレッジ80%以上

### コード品質要件
- [ ] Black フォーマット済み
- [ ] Ruff lintエラーなし
- [ ] Mypy型チェックエラーなし
- [ ] Pre-commit hooks全てパス

### ドキュメント要件
- [ ] `.claude/agents/phase-section-analyst.md` に強度判定セクション追加
- [ ] CLAUDE.md の "Agent System" セクションに強度判定機能の記述追加
- [ ] completion_report.md 作成（実装完了後）

### 検証要件
- [ ] 実データ（recovery/aerobic_base）でフェーズなしのケースが正しく評価される（警告なし）
- [ ] 実データ（tempo/lactate_threshold）でフェーズありのケースが正しく評価される（推奨注意）
- [ ] 実データ（vo2max/anaerobic_capacity/speed）でフェーズありのケースが正しく評価される（警告）
- [ ] 既存のレポート生成が正常に動作する（後方互換性）
- [ ] レポート出力のトーンがトレーニングタイプに応じて変化する

---

## リスク & 対策

### リスク1: training_typeがNULLまたは未知の値
- **対策**: training_typeがNULLの場合はデフォルトで中カテゴリ（tempo_threshold）扱い
- **Mitigation**: 未知のtraining_type値が出現した場合のフォールバックロジックを実装

### リスク2: hr_efficiencyデータが存在しない
- **対策**: hr_efficiency_analysisが取得できない場合はperformance_trendsから推定
- **Mitigation**: エラーハンドリングとログ記録で問題を検出

### リスク3: 既存のレポート表示への影響
- **対策**: analysis_dataのフォーマットを変更せず、トレーニングタイプコンテキストは評価テキスト内に含める
- **Mitigation**: 後方互換性テストで既存レポート生成を確認

### リスク4: レポート出力のトーン変更の影響
- **対策**: レポートテンプレート変更は最小限にし、主にエージェント評価テキストで対応
- **Mitigation**: Phase 2の実データ検証でレポート出力を確認

---

## 実装後のメンテナンス

### 定期的な確認事項
1. 新しいtraining_type値が出現していないか確認（hr_efficiencyテーブル）
2. カテゴリマッピングが適切かユーザーフィードバックで検証
3. レポート出力のトーンが適切かレビュー
4. 後方互換性の維持（既存レポートが正常に表示されるか）

### 今後の改善案
1. training_typeの細分化（例: easy_recovery, base_building, threshold_maintainなど）
2. 個人の履歴に基づく適応的なフェーズ評価（頻繁にウォームアップなしで走る人は警告を減らす）
3. training_typeカテゴリを分析結果のmetadataに明示的に含める（現在は評価テキスト内のみ）
4. レポートテンプレートの完全なトレーニングタイプ対応（現在はオプション）

---

## 参考資料

### 既存プロジェクト
- `docs/project/_archived/2025-10-10_section_analyst_normalized_access/` - エージェント更新の参考例

### 関連ドキュメント
- `.claude/agents/phase-section-analyst.md` - 現在のエージェント定義
- `CLAUDE.md` - Agent System セクション
- `DEVELOPMENT_PROCESS.md` - TDD cycle workflow

### データソース
- `performance_trends` テーブル（avg_pace_seconds_per_km, avg_heart_rate）
- `splits` テーブル（個別スプリットの詳細データ）
