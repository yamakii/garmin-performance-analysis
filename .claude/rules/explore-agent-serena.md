# Explore Agent: Serena 活用ガイドライン

## シンボル探索では Serena を優先使用する

Explore エージェントはコード調査時、以下の手順で Serena を活用すること:

1. **最初に activate**: `mcp__serena__activate_project("/home/yamakii/workspace/garmin-performance-analysis")`
2. **シンボル探索**: `find_symbol`, `get_symbols_overview`, `find_referencing_symbols` を使う
3. **パターン検索**: `search_for_pattern` で柔軟な regex 検索

## いつ Serena を使うか

| ケース | ツール |
|--------|--------|
| クラス・メソッドの定義を探す | `find_symbol` |
| ファイル内のシンボル構造を把握 | `get_symbols_overview` |
| シンボルの参照箇所を追跡 | `find_referencing_symbols` |
| コード内パターン検索 | `search_for_pattern` |
| ファイル名パターンで探す | Glob（Serena 不要） |
| 単純なキーワード grep | Grep（Serena 不要） |

## activate のオーバーヘッド

- activate に数秒かかるため、ファイル名検索や単純 grep だけで済む場合は Glob/Grep で十分
- シンボルの関係性（呼び出し元、継承関係等）を追う必要がある場合は Serena が圧倒的に効率的
- 判断基準: 「シンボルの定義・参照・構造」が必要なら Serena、「テキストパターン」だけなら Glob/Grep
