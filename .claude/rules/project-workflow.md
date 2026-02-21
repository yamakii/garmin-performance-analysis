# Project Workflow Rules

## Plan Mode 内での規模判定と Issue 連携

Plan mode はデフォルトで最初に起動される。規模判定と Issue 連携は **plan mode の探索フェーズ（Phase 1）** で行う。

### Phase 1: 探索と規模判定

Plan mode に入ったら、コード探索と並行して以下を行う:

1. **Issue 番号の確認** — ユーザーの発言、ブランチ名、直前の `/decompose` 結果に Issue 番号があれば `gh issue view {number} --json body,title` で設計を読み込む
2. **規模判定** — コード探索の結果から変更規模を判断:

| 規模 | 判定基準 | アクション |
|------|----------|-----------|
| **Large** | 3+ファイル変更、複数の独立した作業単位、アーキテクチャ変更 | プラン内で `/decompose` を推奨し、ExitPlanMode で提案 |
| **Small + Issue あり** | Issue 番号が指定されている、または Sub-issue として存在 | Issue body の Design/Test Plan をベースにプランを詳細化 |
| **Small + Issue なし** | 1-2ファイル、明確なスコープ | 通常通りプランを書く |

### Phase 2: プラン作成

- **Issue ありの場合**: プランファイルの冒頭に `Issue: #{number}` を記載。Issue body の設計をベースにプランを詳細化
- **Issue なしの場合**: 通常通りプランを書く。必要に応じて plan 承認後に Issue を作成

### Plan 承認後の実装への引き継ぎ

Plan mode 終了時に、tdd-implementer に以下を渡す:
- Issue 番号（ある場合）
- プランファイルのパス
- ワークツリー名の提案

### Issue Body Sync（Plan 承認後）

Issue 番号がある場合、探索で Issue body の Design と Plan 内容に差異があれば:

1. Design セクションを Plan の内容で更新
2. Change Log に `- YYYY-MM-DD (Plan): {差異の概要}` を追記

差異がなければスキップ。詳細は `.claude/rules/issue-sync.md` 参照。

### 大きなタスクの分割シグナル

探索フェーズで以下を検出した場合、プラン内で `/decompose` を推奨:
- "リファクタリング" + 複数モジュール
- "パイプライン" + "分割"/"抽出"
- "アーキテクチャ" + "変更"/"移行"
- 明らかに独立した複数のステップが見える

プラン内での推奨の仕方:
```
このタスクは複数の独立した作業単位に分解できそうです。
`/decompose` で Epic + Sub-issues に分けてから、個別に着手することを推奨します。
```
