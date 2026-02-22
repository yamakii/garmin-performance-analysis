# Project Workflow Rules

## Plan Mode 内での Issue 連携

Plan mode はデフォルトで最初に起動される。Issue 連携は **plan mode の探索フェーズ（Phase 1）** で行う。

**全ての開発タスクで Issue を作成する。** Issue なしでの実装は禁止。

### Phase 1: 探索と分解判定

Plan mode に入ったら、コード探索と並行して以下を行う:

1. **Issue 番号の確認** — ユーザーの発言、ブランチ名、直前の `/decompose` 結果に Issue 番号があれば `gh issue view {number} --json body,title` で設計を読み込む
2. **分解判定** — コード探索の結果から、複数の独立した作業単位があるかを判断:
   - 複数の独立した作業単位がある → プラン内で `/decompose` を推奨
   - 単一の作業単位 → そのままプランを作成

分解を推奨するシグナル:
- "リファクタリング" + 複数モジュール
- "パイプライン" + "分割"/"抽出"
- "アーキテクチャ" + "変更"/"移行"
- 明らかに独立した複数のステップが見える

プラン内での推奨の仕方:
```
このタスクは複数の独立した作業単位に分解できそうです。
`/decompose` で Epic + Sub-issues に分けてから、個別に着手することを推奨します。
```

### Phase 2: プラン作成

- **Issue ありの場合**: プランファイルの冒頭に `Issue: #{number}` を記載。Issue body の設計をベースにプランを詳細化
- **Issue なしの場合**: プランの冒頭に `Issue: TBD (create before implementation)` を記載。ExitPlanMode 後、実装開始前に Issue を作成する

### プランファイル必須フィールド

プランファイルの冒頭に以下を必ず記載する:

```
Issue: #{number} | TBD (create before implementation)
Type: Implementation | Roadmap
```

- `Issue` が未記載のプランは不完全とみなす
- `TBD` の場合、ExitPlanMode 後・実装開始前に Issue を作成し番号を確定する
- `Type` が未記載の場合、`Implementation` とみなす

### プラン種類（Type）の定義

| Type | 内容 | 例 |
|------|------|-----|
| **Implementation** | 具体的なコード変更プラン | 機能追加、バグ修正、リファクタリング |
| **Roadmap** | 優先度付き改善提案リスト | 改善提案10件の優先度マトリクス、技術的負債の整理 |

### Plan 承認後の自動遷移ルール

**実行順序（MANDATORY — スキップ禁止）:**
1. **Issue 作成**: `TBD` の場合、Issue を作成して番号を確定する
2. **Issue sync**: Issue 番号あり + Design と Plan に差異 → Design 更新 + Change Log 追記（詳細は下記「Issue Body Sync」セクション参照）
3. **遷移アクション**: 下表に従い実行

承認後のアクションはプランの Type と分解推奨の有無で決まる。**ユーザーに再確認しない。**

| Type | 条件 | 承認後アクション |
|------|------|-----------------|
| Implementation | 単一作業 | Issue 作成（TBDの場合）→ Issue sync → worktree 作成 → tdd-implementer |
| Implementation | 分解推奨 | Issue sync → `/decompose` → Epic + Sub-issues |
| Roadmap | — | Issue sync → `/decompose` → Epic + Sub-issues |

**Roadmap 固有ルール:**
- 優先度マトリクスがプランに含まれている場合、承認 = その順序での実行承認
- ユーザーに「どれからやるか」を再度聞かない
- 「将来」「backlog」ラベルの項目は Sub-issue 作成するが `backlog` ラベル付与

### Plan 承認後の実装への引き継ぎ

Plan mode 終了時に、tdd-implementer に以下を渡す:
- Issue 番号
- プランファイルのパス
- ワークツリー名の提案

### Issue Body Sync（Plan 承認後）

Issue 番号がある場合、探索で Issue body の Design と Plan 内容に差異があれば:

1. Design セクションを Plan の内容で更新
2. Change Log に `- YYYY-MM-DD (Plan): {差異の概要}` を追記

差異がなければスキップ。詳細は `.claude/rules/issue-sync.md` 参照。
