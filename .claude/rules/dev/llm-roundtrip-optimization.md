# LLM Round-Trip Optimization

## Principle: Minimize LLM round-trips in workflow design

LLMのツール呼び出し1回ごとにAPI往復（数秒〜十数秒）が発生する。
繰り返しパターンを検出したら、Pythonスクリプト1コマンドに集約する。

## When to optimize

- **N回の同じ操作**: Read N files → N tool calls → cleanup のパターン
- **ループ処理**: アクティビティリストを順次処理するワークフロー
- **Read→Parse→Call の連鎖**: ファイル読み込み→データ抽出→MCP呼び出しの繰り返し

## How to optimize

1. **バッチスクリプト化**: N回のMCP呼び出しを1つのPythonスクリプトに集約
2. **ディレクトリ一括処理**: glob("*.json") で全ファイルをループ
3. **JSON出力**: スクリプトの結果はJSON 1行で返す（LLMが1回のRead/Bashで確認可能）
4. **エラーハンドリング内包**: 成功/失敗をスクリプト内で集計し、LLMに判断させない

## Example

```
# BAD: LLM 5 round-trips
for each file in /tmp/analysis_*/
  Read(file)           # round-trip 1-5
  insert_to_db(data)   # round-trip 6-10
rm -rf /tmp/analysis_* # round-trip 11

# GOOD: LLM 1 round-trip
uv run python -m script /tmp/analysis_*  # round-trip 1 (reads, inserts, cleans up)
```

## Design checklist

- [ ] LLMが同じツールを3回以上呼ぶ箇所はないか？
- [ ] Read→Parse→Callの連鎖をスクリプトに置き換えられないか？
- [ ] スクリプトの出力は1回のBash結果で完結するか？
