# 計画: bulk_activity_details_fetch

## Git Worktree情報
- **Worktree Path**: `../garmin-bulk_activity_details_fetch/`
- **Branch**: `feature/bulk_activity_details_fetch`
- **Base Branch**: `main`

---

## 要件定義

### 目的
既存の102アクティビティのうち、101個の欠落している `activity_details.json` ファイルを一括取得し、Phase 0の新しいディレクトリ構造に保存する。これにより、全アクティビティで詳細なチャートデータ（maxchart=2000）が利用可能になる。

### 解決する問題
**現状の課題:**
- 総アクティビティ数: 102個（103ディレクトリ - "." ディレクトリ）
- activity_details.json有り: 1個（activity ID: 20615445009）
- activity_details.json無し: 101個
- 各activityディレクトリには他のAPIファイル（activity.json, splits.json等）が既に存在
- activity_details.jsonが無いと、詳細なチャートデータ（HR/pace/cadenceの秒単位推移）が利用できない

**影響:**
- GarminIngestWorker.load_from_cache() は activity_details.json が無くても動作する（optional扱い）
- しかし、詳細な時系列分析やペース変動の精密な解析ができない
- 一部の高度な分析機能（ペース変動の秒単位分析など）が制限される

### ユースケース
1. **バルク取得スクリプト実行者（開発者）**
   - 既存の101個のアクティビティに対して activity_details.json を一括取得
   - 進捗状況をリアルタイムで確認
   - エラーが発生しても処理を継続し、最後にサマリーを確認

2. **システム運用者**
   - 定期的に欠落しているファイルをチェック
   - 新規アクティビティの追加時に自動でフルデータを取得

3. **データアナリスト**
   - 全アクティビティで統一された詳細データを利用した分析
   - 時系列での精密なパフォーマンス比較

---

## 設計

### アーキテクチャ

**設計方針:**
1. **既存システムとの整合性**: GarminIngestWorker.collect_data() のロジックを再利用
2. **キャッシュ優先**: 既存ファイルは上書きしない（--force オプションで制御）
3. **エラーハンドリング**: 個別のエラーでスクリプト全体が止まらない
4. **進捗表示**: リアルタイムで処理状況を表示（tqdm使用）
5. **API Rate Limit対策**: リクエスト間に待機時間を挿入（デフォルト: 1秒）

**コンポーネント構成:**
```
tools/bulk_fetch_activity_details.py  (新規スクリプト)
  ├─ ActivityDetailsFetcher (メインクラス)
  │   ├─ scan_activities(): 欠落しているファイルを走査
  │   ├─ fetch_single_activity(): 単一アクティビティの取得
  │   └─ fetch_all(): バルク取得実行
  │
  └─ GarminIngestWorker (既存クラス再利用)
      └─ get_garmin_client(): 認証済みGarminクライアント取得
```

**処理フロー:**
```
1. スキャン: data/raw/activity/* を走査
   ↓
2. フィルタリング: activity_details.json が無いディレクトリを抽出
   ↓
3. バルク取得:
   For each activity_id:
     a. Garmin API呼び出し (get_activity_details(maxchart=2000))
     b. ファイル保存 ({activity_id}/activity_details.json)
     c. 待機時間 (rate limit対策)
     d. 進捗表示更新
   ↓
4. サマリー表示:
   - 成功件数
   - スキップ件数
   - エラー件数
   - エラー詳細リスト
```

### データモデル

**Input:**
- 既存のアクティビティディレクトリ: `data/raw/activity/{activity_id}/`
- 必須ファイル: `activity.json` (activity_id検証用)

**Output:**
- 新規ファイル: `data/raw/activity/{activity_id}/activity_details.json`
- サイズ: 約1-3MB/ファイル（maxchart=2000）
- フォーマット: JSON

**ファイル構造:**
```
data/raw/activity/
└── {activity_id}/
    ├── activity.json              [既存]
    ├── activity_details.json      [新規取得対象]
    ├── splits.json                [既存]
    ├── weather.json               [既存]
    ├── gear.json                  [既存]
    ├── hr_zones.json              [既存]
    ├── vo2_max.json               [既存]
    └── lactate_threshold.json     [既存]
```

### API/インターフェース設計

```python
# tools/bulk_fetch_activity_details.py

class ActivityDetailsFetcher:
    """Bulk fetch activity_details.json for all activities."""

    def __init__(
        self,
        raw_dir: Path | None = None,
        delay_seconds: float = 1.0,
        force: bool = False,
    ):
        """
        Initialize fetcher.

        Args:
            raw_dir: Raw data directory (default: data/raw)
            delay_seconds: Delay between API calls (rate limit protection)
            force: Force re-fetch even if file exists
        """

    def scan_activities(self) -> list[tuple[int, Path]]:
        """
        Scan activity directories and find missing activity_details.json.

        Returns:
            List of (activity_id, activity_dir) tuples that need fetching
        """

    def fetch_single_activity(
        self,
        activity_id: int,
        activity_dir: Path,
    ) -> dict[str, Any]:
        """
        Fetch activity_details.json for a single activity.

        Args:
            activity_id: Activity ID
            activity_dir: Activity directory path

        Returns:
            Result dict with status ('success', 'skipped', 'error')
        """

    def fetch_all(self) -> dict[str, Any]:
        """
        Fetch all missing activity_details.json files.

        Returns:
            Summary dict with success/skip/error counts and details
        """


# CLI Interface
def main():
    """
    CLI entry point.

    Usage:
        python tools/bulk_fetch_activity_details.py [--force] [--delay 1.5]

    Options:
        --force: Force re-fetch even if file exists
        --delay: Delay between API calls in seconds (default: 1.0)
        --dry-run: Show what would be fetched without actually fetching
    """
```

**実行例:**
```bash
# 通常実行（欠落ファイルのみ取得）
uv run python tools/bulk_fetch_activity_details.py

# 強制再取得（全ファイル上書き）
uv run python tools/bulk_fetch_activity_details.py --force

# 待機時間を2秒に設定（rate limit対策を強化）
uv run python tools/bulk_fetch_activity_details.py --delay 2.0

# Dry run（実際に取得せず、対象ファイルを確認）
uv run python tools/bulk_fetch_activity_details.py --dry-run
```

---

## テスト計画

### Unit Tests

- [ ] **test_scan_activities**: ディレクトリスキャンが正しく動作する
  - 既存のactivity_details.jsonはスキップされる
  - 無効なディレクトリ（activity.json無し）はスキップされる
  - 正しいactivity_idのリストが返される

- [ ] **test_fetch_single_activity_success**: 単一アクティビティの取得が成功する
  - APIから正しくデータが取得される
  - ファイルが正しいパスに保存される
  - JSONフォーマットが正しい

- [ ] **test_fetch_single_activity_skip**: 既存ファイルがスキップされる（force=False）
  - activity_details.jsonが既に存在する場合
  - status='skipped'が返される
  - ファイルが上書きされない

- [ ] **test_fetch_single_activity_force**: force=Trueで上書きされる
  - 既存ファイルがあっても再取得される
  - status='success'が返される

- [ ] **test_fetch_single_activity_api_error**: APIエラーのハンドリング
  - 認証エラー時にstatus='error'が返される
  - ネットワークエラー時にstatus='error'が返される
  - エラーメッセージが記録される

### Integration Tests

- [ ] **test_bulk_fetch_with_mock_api**: モックAPIを使ったバルク取得
  - 複数アクティビティの一括取得が成功する
  - 進捗表示が正しく更新される
  - サマリーが正しく生成される

- [ ] **test_rate_limit_handling**: Rate limit保護が動作する
  - 各API呼び出し間に指定された待機時間がある
  - 429エラー時に適切にリトライされる（オプション機能）

- [ ] **test_partial_failure_recovery**: 部分的な失敗時の継続処理
  - 一部のアクティビティでエラーが発生しても処理が継続する
  - 成功/失敗が正しくカウントされる
  - エラーリストに失敗したアクティビティが記録される

- [ ] **test_existing_workflow_compatibility**: 既存ワークフローとの互換性
  - 取得したファイルがGarminIngestWorker.load_from_cache()で読み込める
  - 既存のperformance.json生成パイプラインが正常に動作する

### Performance Tests

- [ ] **test_performance_101_activities**: 101アクティビティの処理時間
  - 目標: 101アクティビティを10分以内に処理（delay=1.0の場合）
  - 計算: 101 activities × (1s API + 1s delay) = 約202秒 ≈ 3.4分

- [ ] **test_memory_usage**: メモリ使用量が適切
  - 大量のアクティビティ処理中もメモリリークが無い
  - ピークメモリ使用量 < 500MB

- [ ] **test_error_rate**: エラー率が低い
  - APIエラー率 < 5%（リトライ後）
  - ファイル書き込みエラー率 = 0%

---

## 実装フェーズ

### Phase 1: Core Implementation（優先度: 高）
1. ActivityDetailsFetcherクラスの実装
2. scan_activities()メソッド: ディレクトリ走査とフィルタリング
3. fetch_single_activity()メソッド: 単一アクティビティ取得
4. エラーハンドリングとロギング

### Phase 2: Bulk Processing（優先度: 高）
1. fetch_all()メソッド: バルク取得実行
2. tqdmによる進捗表示
3. Rate limit保護（delay_seconds）
4. サマリー生成

### Phase 3: CLI Interface（優先度: 中）
1. argparse設定（--force, --delay, --dry-run）
2. main()関数: エントリーポイント
3. ヘルプメッセージとドキュメント

### Phase 4: Testing（優先度: 高）
1. Unit tests実装（pytest）
2. Integration tests実装（モックAPI使用）
3. Performance tests実装

### Phase 5: Documentation & Deployment（優先度: 中）
1. README更新（Usage sectionに追記）
2. CLAUDE.md更新（Common Development Commands）
3. 実環境での実行とバリデーション
4. completion_report.md作成

---

## 受け入れ基準

### 機能要件
- [ ] 101個の欠落している activity_details.json を取得できる
- [ ] 既存ファイルはデフォルトでスキップされる（--forceで上書き可能）
- [ ] API rate limit対策が実装されている（デフォルト1秒待機）
- [ ] エラーが発生しても処理が継続し、最後にサマリーが表示される
- [ ] 進捗状況がリアルタイムで表示される（tqdm使用）

### 非機能要件
- [ ] 101アクティビティの処理時間が10分以内（delay=1.0）
- [ ] メモリ使用量が500MB以下
- [ ] エラー率が5%以下（リトライ後）

### コード品質
- [ ] 全Unit testsがパスする（カバレッジ80%以上）
- [ ] 全Integration testsがパスする
- [ ] Performance testsがパスする
- [ ] Black, Ruff, Mypyのチェックがパスする
- [ ] Pre-commit hooksがパスする

### ドキュメント
- [ ] planning.mdが完成している
- [ ] completion_report.mdが作成されている
- [ ] CLAUDE.mdに使用方法が追記されている
- [ ] コード内にdocstringが適切に記述されている

---

## リスク管理

### 想定されるリスク

1. **Garmin API Rate Limiting**
   - 影響: 大量のリクエストでAPI制限に引っかかる可能性
   - 対策: デフォルト1秒待機、--delayオプションで調整可能
   - 緩和策: 429エラー時の自動リトライ（exponential backoff）

2. **認証トークンの有効期限**
   - 影響: 長時間実行中にトークンが期限切れになる可能性
   - 対策: GarminIngestWorker.get_garmin_client()のシングルトン設計を活用
   - 緩和策: 認証エラー時に自動再認証（既存実装で対応済み）

3. **ディスク容量不足**
   - 影響: 101個 × 2MB = 約202MB必要
   - 対策: 事前に空き容量をチェック（オプション機能）
   - 緩和策: ディスク容量が不足した場合のエラーメッセージ

4. **ネットワーク不安定**
   - 影響: API呼び出し失敗率が上昇
   - 対策: 各API呼び出しにtry-exceptを設定
   - 緩和策: エラー発生時も処理継続、最後にリトライリストを表示

5. **Garmin APIの仕様変更**
   - 影響: activity_details取得方法が変更される可能性
   - 対策: 既存のGarminIngestWorker実装に依存し、変更箇所を最小化
   - 緩和策: エラー発生時に詳細なエラーメッセージを表示

---

## 実装ノート

### 参考実装
- **GarminIngestWorker.collect_data()**: activity_details.json取得ロジック（L403-418）
  ```python
  activity_file = activity_dir / "activity_details.json"
  if activity_file.exists():
      # Cache hit
  else:
      activity_data = client.get_activity_details(activity_id, maxchart=2000)
      with open(activity_file, "w", encoding="utf-8") as f:
          json.dump(activity_data, f, ensure_ascii=False, indent=2)
  ```

- **GarminIngestWorker.get_garmin_client()**: シングルトン認証クライアント（L140-170）
  ```python
  @classmethod
  def get_garmin_client(cls) -> Garmin:
      if cls._garmin_client is None:
          cls._garmin_client = Garmin(email, password)
          cls._garmin_client.login()
      return cls._garmin_client
  ```

### ベストプラクティス
1. **キャッシュ優先**: 既存ファイルは上書きしない（--force除く）
2. **エラー継続**: 個別のエラーでスクリプト全体を停止しない
3. **進捗表示**: ユーザーが処理状況を把握できるようにする
4. **ロギング**: 各処理のログを記録（INFO/WARNING/ERROR）
5. **サマリー**: 処理完了後に成功/失敗の統計を表示

### 注意事項
- Garmin APIの利用規約に準拠する（過度なリクエストを避ける）
- 環境変数（GARMIN_EMAIL, GARMIN_PASSWORD）が設定されていることを前提とする
- 既存のGarminIngestWorkerの実装に依存するため、その動作を変更しない

---

## 実装進捗

- [ ] Phase 1: Core Implementation
- [ ] Phase 2: Bulk Processing
- [ ] Phase 3: CLI Interface
- [ ] Phase 4: Testing
- [ ] Phase 5: Documentation & Deployment
