---
paths:
  - "pyproject.toml"
  - "uv.lock"
  - "**/package.json"
  - ".pre-commit-config.yaml"
  - ".github/**"
  - "docker/**"
---

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

## Sandbox freeze（#1050）

sandbox（`docker/**`、`docker/managed-settings.json`、sandbox に触れる hook）は**完成扱いで凍結**する。
2026-09-07 だけで sandbox の PR が 6 本（#1029〜#1036）出て bubblewrap を同日中に導入・撤去し、32 GB 化（#1011）で
SIGKILL は解消済み。故障の無い改良は churn にしかならない。変更してよいのは次の 3 つだけ:

1. **再現可能な故障**が Issue に記録されている（失敗したコマンドと出力、再現手順つき）。「念のため」「より安全に」は不可
2. **security advisory**（base image / 同梱ツールの脆弱性）
3. **Dependabot の base-image bump**（`docker-build` CI + `sandbox-smoke.sh` がゲート）

spike / 探索的な hardening は起こさない。提案したくなったら Issue に「観測した故障」を書いて止める。
`docker-build` job と `sandbox-smoke.sh` は残すので、凍結によって回帰検知が減ることはない。

## 実行時の注意（sandbox / worktree）

- sandbox の `uv` は wrapper（`docker/uv-wrapper.sh` + `docker/lib/uv-venv.sh`）で、**checkout × package ごとに別の venv** を `/home/claude/uv-venvs/` 下に割り当てる（#1047）。`ci-check.sh` も同じ helper を使う。全体共通の `UV_PROJECT_ENVIRONMENT` を image や `.envrc` に置かないこと（置くと旧来の共有 venv 事故に戻る）。web と server の sync を並列に走らせても互いの extras は消えない
- `uv lock --upgrade` は pyproject の制約内で最新に上げる。制約が `>=` のみのパッケージは major も上がるため、差分の `Update x vA -> vB` を必ず目視し major を分離判断する
- pre-commit の `ruff-pre-commit` / `black` rev は uv.lock の ruff / black と同じバージョンに揃える（ローカル pre-commit と CI の lint 結果を一致させるため）
- 変更後の検証は `scripts/ci-check.sh` exit 0 が完了条件（`worktree-validation-protocol.md` の L2 相当）。lockfile-only の PR でも CI は `uv.lock` をフィルタに含めているため lint-and-test が走る
