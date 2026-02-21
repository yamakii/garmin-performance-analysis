# Bash Style Rules

## チェーンコマンド禁止

`&&`, `||`, `;` でコマンドを繋がない。個別に許可済みのコマンドでもチェーンすると再許可プロンプトが発生する。

## 代替手段

- **独立したコマンド**: 並列の Bash tool call で実行
- **順序依存**: `&&` を使うが、最小限に留める（例: `git add && git commit`）

## 例

```bash
# BAD: 再許可が必要になる
ls packages && echo "done"

# GOOD: 並列 Bash tool call
# Call 1: ls packages
# Call 2: echo "done"

# OK: 順序依存（前のコマンドの成功が必須）
git add file.py && git commit -m "msg"
```
