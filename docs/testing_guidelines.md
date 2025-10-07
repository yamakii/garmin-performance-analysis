# Testing Guidelines

## Test Markers

### `@pytest.mark.unit`
- 単体テスト
- 外部依存なし（ファイルシステム、データベース、API不要）
- 高速実行

### `@pytest.mark.integration`
- 統合テスト
- ファイルシステム、DuckDB、Parquetファイルなどの外部リソースを使用
- **pre-commit hookで実行される**

### `@pytest.mark.garmin_api`
- Garmin API認証が必要なテスト
- Rate limit対策のため、**pre-commit hookから除外される**
- 手動実行のみ: `pytest -m garmin_api`

### `@pytest.mark.performance`
- パフォーマンステスト
- 実行時間の測定やベンチマーク

## Pre-commit Behavior

```bash
# Pre-commit hookで実行されるテスト
pytest -m "not garmin_api"  # garmin_apiマーカー以外のすべてのテスト
```

## Test Execution Examples

```bash
# Unit testsのみ
pytest -m unit

# Integration testsのみ
pytest -m integration

# Garmin API testsのみ（手動実行）
pytest -m garmin_api

# Garmin API tests以外すべて（pre-commitと同じ）
pytest -m "not garmin_api"

# すべてのテスト
pytest
```

## Best Practices

1. **Garmin API認証が必要なテストには必ず `@pytest.mark.garmin_api` を付ける**
   - Rate limitを避けるため、pre-commitでは実行されない

2. **Integration testsはキャッシュファイルを使う**
   - `data/raw/` にキャッシュファイルがある場合、API呼び出しは不要
   - キャッシュファイル存在確認: `assert cache_file.exists()`

3. **複数マーカーの併用**
   ```python
   @pytest.mark.integration
   @pytest.mark.garmin_api
   def test_api_integration():
       # API認証 + 統合テスト
       pass
   ```

## Garmin API Rate Limit

- Garmin APIには429 Too Many Requestsのrate limitがある
- 認証失敗が続くと一時的にブロックされる
- `@pytest.mark.garmin_api` マーカーで隔離し、手動実行のみにする
