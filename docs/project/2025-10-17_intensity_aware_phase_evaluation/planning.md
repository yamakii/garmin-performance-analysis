# 計画: Intensity-Aware Phase Evaluation

## プロジェクト情報
- **プロジェクト名**: `intensity_aware_phase_evaluation`
- **作成日**: `2025-10-17`
- **ステータス**: 計画中
- **関連Issue**: (作成後にリンクを追加)

## 要件定義

### 目的

アクティビティの強度（intensity）に基づいてフェーズ評価ロジックを適応させ、低～中強度走で不適切な警告が出るのを防ぐ。

### 解決する問題

**現状の問題:**
- phase-section-analystは全てのランニングで3フェーズ（warmup/run/cooldown）または4フェーズ（warmup/run/recovery/cooldown）を想定
- 低～中強度走（ジョグ、リカバリー走）では：
  - ウォームアップなしで始まることが一般的
  - クールダウンなしで終わることが一般的
  - 全体が1つのメインフェーズのみで構成される
- 現在の実装では、これらのケースで不適切な警告（「ウォームアップがないため怪我リスクが高まる」等）を出している可能性がある

**影響:**
- ユーザーが低強度走でも「ウォームアップ不足」の警告を受け取る
- フェーズ評価の信頼性が低下
- トレーニング強度に応じた適切なフィードバックができない

### ユースケース

1. **低強度走（Easy/Recovery Run）**
   - 平均ペース > 5:30/km または 平均心拍 < 閾値の70%
   - ウォームアップ・クールダウンなしでも警告を出さない
   - フェーズ評価: "低強度走のため、ウォームアップ・クールダウンはオプショナル"

2. **中強度走（Tempo/Base Run）**
   - 平均ペース 4:30-5:30/km または 平均心拍 70-85%
   - ウォームアップ・クールダウンがあれば推奨、なければ軽い注意
   - フェーズ評価: "テンポ走では適切なウォームアップが推奨されます"

3. **高強度走（Threshold/Interval）**
   - 平均ペース < 4:30/km または 平均心拍 > 85%
   - ウォームアップ・クールダウンを強く推奨、なければ警告
   - フェーズ評価: "高強度トレーニングではウォームアップが必須です"

4. **インターバルトレーニング（4フェーズ）**
   - recovery_splitsが存在する場合
   - 常に高強度扱い（既存の評価ロジックを維持）

---

## 設計

### アーキテクチャ

```
User Request
    ↓
phase-section-analyst (updated)
    ↓
1. Intensity Determination Logic (NEW)
   - Input: performance_trends data (avg_pace, avg_hr)
   - Output: intensity_level ("easy", "moderate", "high")
    ↓
2. Phase Structure Detection (existing)
   - Input: performance_trends.recovery_splits
   - Output: phase_count (3 or 4)
    ↓
3. Phase Evaluation with Intensity Context (updated)
   - Input: intensity_level, phase_data
   - Output: context-aware evaluation text
    ↓
4. Insert to DuckDB (existing)
   - section_type: "phase"
   - analysis_data: {warmup_evaluation, run_evaluation, [recovery_evaluation], cooldown_evaluation}
```

**変更箇所:**
- phase-section-analyst エージェント定義のみを更新
- DuckDBスキーマは変更なし
- 他のエージェント（split/summary/efficiency/environment）には影響なし

### データモデル

**既存のDuckDBスキーマ（変更なし）:**

```sql
-- performance_trends テーブル (使用フィールド)
CREATE TABLE performance_trends (
    activity_id BIGINT PRIMARY KEY,
    avg_pace_seconds_per_km DOUBLE,           -- 強度判定に使用
    avg_heart_rate INTEGER,                   -- 強度判定に使用
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

**新規ロジック（コード内のみ、DBスキーマ変更なし）:**

```python
# Intensity Level Enumeration (agent prompt内で定義)
intensity_levels = {
    "easy": {
        "pace_threshold": 330,  # 5:30/km in seconds
        "hr_threshold_percent": 0.70,
        "warmup_required": False,
        "cooldown_required": False,
        "warning_level": "none"
    },
    "moderate": {
        "pace_range": (270, 330),  # 4:30-5:30/km
        "hr_range_percent": (0.70, 0.85),
        "warmup_required": "recommended",
        "cooldown_required": "recommended",
        "warning_level": "light"
    },
    "high": {
        "pace_threshold": 270,  # < 4:30/km
        "hr_threshold_percent": 0.85,
        "warmup_required": True,
        "cooldown_required": True,
        "warning_level": "strong"
    }
}
```

### API/インターフェース設計

**既存MCPツール（変更なし）:**

```python
# phase-section-analyst で使用
mcp__garmin_db__get_performance_trends(activity_id: int) -> dict
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

## 新機能: 強度判定ロジック

1. performance_trendsから avg_pace_seconds_per_km, avg_heart_rate を取得
2. 以下の基準で強度レベルを判定:
   - **Easy/Recovery**: avg_pace > 330 sec/km (5:30/km) OR avg_hr < 70% threshold
   - **Moderate (Tempo/Base)**: avg_pace 270-330 sec/km (4:30-5:30/km) OR avg_hr 70-85%
   - **High (Threshold/Interval)**: avg_pace < 270 sec/km (4:30/km) OR avg_hr > 85%
3. フェーズ評価に強度コンテキストを含める

## 評価ガイドライン（強度別）

### Easy/Recovery (低強度)
- ウォームアップ評価:
  - **存在する場合**: 「低強度走ではオプショナルですが、適切なウォームアップができています」
  - **存在しない場合**: 「低強度走のため、ウォームアップなしでも問題ありません」（警告なし）
- クールダウン評価:
  - **存在する場合**: 「丁寧なクールダウンができています」
  - **存在しない場合**: 「低強度走のため、クールダウンなしでも問題ありません」（警告なし）

### Moderate (中強度)
- ウォームアップ評価:
  - **存在する場合**: 「テンポ走に適したウォームアップができています」
  - **存在しない場合**: 「テンポ走では軽いウォームアップが推奨されます」（軽い注意）
- クールダウン評価:
  - **存在する場合**: 「適切なクールダウンができています」
  - **存在しない場合**: 「クールダウンがあるとより良いでしょう」（軽い注意）

### High (高強度)
- ウォームアップ評価:
  - **存在する場合**: 「高強度トレーニングに必要なウォームアップができています」（詳細評価）
  - **存在しない場合**: 「高強度走ではウォームアップが必須です。怪我リスクが高まります」（警告）
- クールダウン評価:
  - **存在する場合**: 「高強度後の適切なクールダウンができています」（詳細評価）
  - **存在しない場合**: 「高強度走後はクールダウンが重要です。疲労回復が遅れる可能性があります」（警告）
```

---

## 実装フェーズ

### Phase 1: エージェントプロンプト更新

**実装順序: TDD cycle (Red → Green → Refactor)**

#### 1.1 強度判定ロジック追加
- **Test**: 強度判定の単体テスト（easy/moderate/high の境界値）
- **Implementation**: `.claude/agents/phase-section-analyst.md` に強度判定セクション追加
- **Refactor**: 判定基準の明確化、境界値の文書化

#### 1.2 フェーズ評価ガイドライン更新
- **Test**: 強度別フェーズ評価のテスト（ウォームアップあり/なし × 3強度 = 6パターン）
- **Implementation**: 評価ガイドラインに強度別の記述を追加
- **Refactor**: 評価テキストのトーン統一

#### 1.3 出力形式の更新
- **Test**: 出力JSONにintensity_contextが含まれることを確認
- **Implementation**: analysis_dataに強度コンテキストを含める
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
- [ ] phase-section-analystが強度判定を実行できる
- [ ] 低強度走でウォームアップ・クールダウンなしでも警告が出ない
- [ ] 中強度走でウォームアップ・クールダウンがない場合、軽い注意が出る
- [ ] 高強度走でウォームアップ・クールダウンがない場合、警告が出る
- [ ] インターバルトレーニング（4フェーズ）の既存評価ロジックが維持されている
- [ ] section_analysesテーブルに強度コンテキストが保存される

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
- [ ] 実データ（低強度走）でフェーズなしのケースが正しく評価される
- [ ] 実データ（中強度走）でフェーズありのケースが正しく評価される
- [ ] 実データ（高強度走）でフェーズありのケースが正しく評価される
- [ ] 既存のレポート生成が正常に動作する（後方互換性）

---

## リスク & 対策

### リスク1: 強度判定の閾値が不適切
- **対策**: 実データで複数のアクティビティをテストし、閾値を調整
- **Mitigation**: Phase 2で実データ検証を実施し、必要に応じて閾値を微調整

### リスク2: 心拍閾値の個人差
- **対策**: 現時点では固定値（70%, 85%）を使用、将来的には個人の閾値を考慮
- **Mitigation**: 心拍閾値が不明な場合はペースベースの判定を優先

### リスク3: 既存のレポート表示への影響
- **対策**: analysis_dataのフォーマットを変更せず、強度コンテキストは評価テキスト内に含める
- **Mitigation**: 後方互換性テストで既存レポート生成を確認

### リスク4: インターバルトレーニングの判定
- **対策**: recovery_splitsが存在する場合は常に高強度扱い（既存ロジック維持）
- **Mitigation**: 4フェーズ判定を強度判定より優先

---

## 実装後のメンテナンス

### 定期的な確認事項
1. 強度判定の閾値が実データに適合しているか確認
2. 新しいトレーニングタイプ追加時の強度判定ロジック更新
3. ユーザーフィードバックに基づく評価テキストの改善

### 今後の改善案
1. 個人の心拍閾値データ（lactate_threshold, vo2_maxテーブル）を活用した動的閾値
2. 強度レベルを3段階から5段階に拡張（very_easy, easy, moderate, hard, very_hard）
3. 強度レベルを分析結果のmetadataに明示的に含める（現在は評価テキスト内のみ）
4. トレーニング履歴に基づく適応的な閾値調整

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
