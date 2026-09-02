# Maintenance Policy（依存更新・セキュリティ）

継続メンテナンスの仕組みと判断基準。運用ランブックは `docs/maintenance.md`、実行手順は `/maintenance` skill。

## 仕組み（自動で回る部分）

| 経路 | トリガー | 役割 |
|------|----------|------|
| Dependabot (`.github/dependabot.yml`) | 毎週月曜 09:00 JST（actions/docker は月次） | uv / npm / GitHub Actions / Docker の更新 PR。minor+patch は ecosystem ごとに1 PR にグループ化、major は個別 PR |
| `dependabot-auto-merge.yml` | Dependabot PR 作成時 | minor/patch PR に GitHub auto-merge を有効化（`ci-guard` green で自動マージ）。major はコメントのみ |
| `security-audit.yml` | 毎週月曜 + lockfile 変更 PR + 手動 | `pip-audit`（uv.lock）+ `npm audit --audit-level=high`。検出時は `security-audit` ラベルの Issue を自動起票/更新 |
| `/maintenance` skill | 人間 or 定期ルーチンが起動 | 上記で拾えない残り（major の判断材料整理、pre-commit rev 同期、上限ピンの見直し）を1セッションで処理 |

## 判断基準

- **security（advisory あり）**: 即時。fix 版があれば patch/minor/major を問わず当週中に適用。fix 版が無ければ影響評価を Issue に残す
- **minor / patch**: 自動（Dependabot + auto-merge）。`ci-guard` が唯一のゲートなので、**CI が exercise しない挙動変更は人が拾う前提を置かない**（テストで守る）
- **major**: 人間判断。Dependabot の PR に changelog / migration の要点をコメントし、必要ならコード変更を伴う Issue に切り出す。「単に最新だから」で上げない
- **上限ピン（`<N`）**: 例外扱い。理由（移行未調査 / 既知の破壊的変更）を pyproject のコメント or Issue に残し、`/maintenance` の度に解除可否を再判定する。現行: `mcp>=2.1.1,<3`（低レベル `Server` のハンドラ登録が major で変わるため、次の major も同様に調査が要る、#953）
- **ランタイム major（Python / Node LTS）**: 体験・環境に影響するため必ず人間に確認してから変更する

## 実行時の注意（sandbox / worktree）

- `UV_PROJECT_ENVIRONMENT` が設定された環境（Docker sandbox 等）では **全 worktree・全パッケージが1つの venv を共有する**。`uv sync` を並列で走らせると互いの依存を消し合う（`packages/garmin-web` の sync が server の dev extras を消し、mypy/pytest-xdist が壊れる）。`scripts/ci-check.sh` の順序どおり**直列**で回すこと
- `uv lock --upgrade` は pyproject の制約内で最新に上げる。制約が `>=` のみのパッケージは major も上がるため、差分の `Update x vA -> vB` を必ず目視し major を分離判断する
- pre-commit の `ruff-pre-commit` / `black` rev は uv.lock の ruff / black と同じバージョンに揃える（ローカル pre-commit と CI の lint 結果を一致させるため）
- 変更後の検証は `scripts/ci-check.sh` exit 0 が完了条件（`dev-reference.md` §3 の L2 相当）。lockfile-only の PR でも CI は `uv.lock` をフィルタに含めているため lint-and-test が走る
