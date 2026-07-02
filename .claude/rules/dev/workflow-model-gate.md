# Workflow Agent Model Gate

`.claude/workflows/*.js` の各 `agent()` 呼び出しは **許可モデル（最大 opus）を明示解決できること**を
必須とする。model も agentType も無い `agent()`、および `model: inherit` はセッションモデル
（Fable 等の上位モデル）を暗黙継承し、コスト増・非決定性の温床になる。CI（`meta-checks` →
`scripts/check-claude-scripts.sh` → `scripts/check-workflow-agent-model.mjs`）が違反を exit 1 で弾く。

## 許可モデル（opus が上限）

```
haiku / sonnet / opus
```

これ以外の値（`inherit` や上位セッションモデル名）は**すべて違反**。`inherit` はかつて
「明示的オプトイン」として許容していたが、上位モデルを暗黙継承するため **Issue #723 で廃止**した。

## ルール

各 `agent()` は次のいずれかで **許可モデル**を解決すること:

1. **`model:` オプションを明示**し、その string literal 値が許可モデル（`haiku`/`sonnet`/`opus`）で
   あること。許可リスト外の literal（例: `model: 'fable'`）→ **違反**。
2. **`agentType:` を指定**し、その def（`.claude/agents/<name>.md`）frontmatter が **許可モデルの
   `model:`** を宣言していること（`model: inherit` や許可リスト外は**違反**）。

満たさない（model も agentType も無い / callsite model が許可リスト外 / agentType の def が
model 未宣言 or def 不在 or 許可リスト外 or inherit）→ **違反**。

### 動的 agentType は許容

`agentType` の値が三項演算子・変数など**静的解決できない**式のときは許容する
（分岐先 def を静的に特定できないため author を信頼。分岐先 def が model を宣言している
ことは運用で担保する）。

例:
```js
// OK: 静的に unified-section-analyst / summary-section-analyst のいずれか
agentType: s === 'summary' ? 'summary-section-analyst' : 'unified-section-analyst'
```
どちらの def も**許可モデルの** `model:` を宣言していれば実質安全。gate は静的解決不能として素通しする。

## model 選択の目安

- **純オーケストレーション**（MCP/bash 実行 + JSON echo。分析的推論なし）→ `model: 'haiku'`。
  例: `analyze-activity.js` の fetch / merge。
- **分析・生成**（推論が価値の中心）→ agentType の def で `sonnet` 等を宣言、または `model:` で明示。

## チェッカー

- 実装: `scripts/check-workflow-agent-model.mjs`（純関数 + CLI）。
- 純関数テスト: `.claude/workflows/tests/check-agent-model.test.mjs`（`node --test`）。
- CI 統合: `scripts/check-claude-scripts.sh` が CLI を実行し、違反で status=1。

新しい workflow / `agent()` を追加したら、ローカルで
`node scripts/check-workflow-agent-model.mjs` を回して green を確認する。
