# Test Fixtures

このディレクトリには、テスト用のダミーデータが含まれています。

## 構造

```
tests/fixtures/
├── activity/
│   └── 12345678901/          # ダミーアクティビティID
│       └── activity_details.json
└── README.md
```

## ダミーデータの特徴

- **activity_details.json**: 10秒間の最小限のメトリクスデータ
  - Activity ID: `12345678901` (実在しないダミーID)
  - 6つのメトリクス: HR, Speed, Cadence, GCT, VO, Timestamp
  - 10測定ポイント（1秒ごと）
  - すべての値はテスト用のダミー値

## 使用方法

テストコードでは以下のように使用します:

```python
from pathlib import Path

def test_example():
    fixture_path = Path(__file__).parent.parent / "fixtures"
    activity_id = 12345678901

    # Use fixture data
    loader = ActivityDetailsLoader(base_path=fixture_path)
    data = loader.load_activity_details(activity_id)
```

## データの更新

新しいテストケースで追加のデータが必要な場合は:

1. 既存の実データを参考にする
2. 個人情報（位置情報など）を除外
3. ダミー値に置き換える
4. 最小限の構造にする
5. このREADMEを更新する
