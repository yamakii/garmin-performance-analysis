# GitHub公開チェックリスト

このドキュメントは、個人データを含むGarminプロジェクトを安全にGitHubに公開するための手順をまとめたものです。

## 📋 作業概要

### A. データ外部配置（プライバシー保護）
個人の健康データ（体重、走行ルート等）をプロジェクト外に配置し、誤公開を防止

### B. Git履歴クリーンアップ
既に履歴に含まれている個人データを完全削除

### C. GitHub公開準備
README、LICENSE、最終確認

---

## A. データ外部配置（4ステップ）

### A-1: 配置先ディレクトリ作成

**推奨配置先:**
```bash
~/garmin_data/          # Option 1: ホームディレクトリ直下（推奨）
~/Documents/garmin_data/  # Option 2: ドキュメントフォルダ
```

**コマンド:**
```bash
# 配置先を決める（例: ホームディレクトリ）
GARMIN_DATA_LOCATION=~/garmin_data

# ディレクトリ作成
mkdir -p $GARMIN_DATA_LOCATION
```

### A-2: data/とresult/を移動

**現在のサイズ:**
- data/: 354MB
- result/: 124KB

**コマンド:**
```bash
# データを移動
mv data/* $GARMIN_DATA_LOCATION/data/
mv result/* $GARMIN_DATA_LOCATION/results/

# 元のディレクトリは空のまま残す（.gitkeepファイルがあるため）
ls -la data/     # .gitkeepのみ残っていることを確認
ls -la result/   # 空であることを確認
```

### A-3: .envファイル作成と設定

**コマンド:**
```bash
# プロジェクトルートに移動
cd /home/yamakii/workspace/claude_workspace/garmin

# .env.exampleをコピー
cp .env.example .env

# .envを編集（絶対パスで指定）
cat > .env << 'EOF'
# Garmin Performance Analysis - Data Directory Configuration
# Copy this file to .env and customize the paths below

# Base data directory (absolute path recommended for safety)
GARMIN_DATA_DIR=/home/yamakii/garmin_data/data

# Result directory (absolute path recommended for safety)
GARMIN_RESULT_DIR=/home/yamakii/garmin_data/results
EOF

# .envが正しく作成されたか確認
cat .env
```

### A-4: 動作確認テスト実行

**テスト内容:**
- パスユーティリティのテスト
- GarminIngestWorkerのテスト
- Databaseのテスト

**コマンド:**
```bash
# 環境変数が読み込まれるか確認
uv run python -c "from tools.utils.paths import get_data_base_dir, get_result_dir; print(f'Data: {get_data_base_dir()}'); print(f'Result: {get_result_dir()}')"

# パスユーティリティのテスト
uv run pytest tests/utils/test_paths.py -v

# GarminIngestWorkerのテスト
uv run pytest tests/ingest/test_garmin_worker_paths.py -v

# Databaseのテスト
uv run pytest tests/database/test_database_paths.py -v

# 全テストが通ることを確認
uv run pytest
```

**期待結果:**
- すべてのテストがpass
- データパスが $GARMIN_DATA_DIR を指している
- 結果パスが $GARMIN_RESULT_DIR を指している

---

## B. Git履歴クリーンアップ（BFG使用）

### 問題のあるファイル

以下のファイルがGit履歴に含まれており、個人の体重・BMIデータが記録されています：

1. `data/weight_cache/weight_index.json` (旧形式)
2. `data/weight/index.json` (新形式)

**含まれる個人データ例:**
```json
{
  "2025-09-29": {
    "weight": 76.599,
    "bmi": 27.5,
    ...
  }
}
```

### B-1: BFG Repo-Cleanerインストール

**Ubuntu/Debian:**
```bash
sudo apt install bfg
```

**または直接ダウンロード:**
```bash
wget https://repo1.maven.org/maven2/com/madgag/bfg/1.14.0/bfg-1.14.0.jar
alias bfg='java -jar bfg-1.14.0.jar'
```

### B-2: バックアップ作成

```bash
# リポジトリ全体をバックアップ
cd /home/yamakii/workspace/claude_workspace/
tar -czf garmin-backup-$(date +%Y%m%d).tar.gz garmin/

# バックアップが作成されたことを確認
ls -lh garmin-backup-*.tar.gz
```

### B-3: Git履歴からファイル削除

⚠️ **警告:** この操作は履歴を書き換えます。他のworktreeがある場合は先に削除してください。

```bash
# プロジェクトルートに移動
cd /home/yamakii/workspace/claude_workspace/garmin

# 現在のworktreeを確認
git worktree list

# 他のworktreeがあれば削除（必要に応じて）
# git worktree remove ../garmin-{project_name}

# BFGでファイルを削除
bfg --delete-files 'weight_index.json'
bfg --delete-files 'index.json' --no-blob-protection

# Git履歴をクリーンアップ
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 結果を確認
git log --all --pretty=format: --name-only | grep -E 'index.json' | sort -u
# 何も表示されなければ成功
```

### B-4: 削除確認

```bash
# 履歴に残っていないことを確認
git log --all -- data/weight_cache/weight_index.json
git log --all -- data/weight/index.json
# "fatal: ambiguous argument" が表示されればOK（ファイルが存在しない）
```

---

## C. GitHub公開準備

### C-1: README.md作成

プロジェクトの概要、セットアップ手順、使い方を記載

**必須項目:**
- プロジェクト概要
- 機能一覧
- セットアップ手順（.env設定含む）
- 使い方
- MCP統合ガイド
- ライセンス情報

### C-2: LICENSE追加

**推奨ライセンス:**
- MIT License: オープンソースとして広く使える
- Apache 2.0: 特許条項が必要な場合

**コマンド例（MIT License）:**
```bash
cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2025 [Your Name]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
EOF
```

### C-3: 最終チェック

#### .gitignore確認

```bash
# .gitignoreが正しいことを確認
cat .gitignore | grep -E '^(data|result|\.env)'

# 期待される出力:
# data/raw/*
# data/performance/*
# ...
# result/
# .env
```

#### Git statusチェック

```bash
git status

# 以下が含まれていないことを確認:
# - data/配下のファイル（.gitkeepを除く）
# - result/配下のファイル
# - .envファイル
```

#### 追跡されているファイルの確認

```bash
# data/やresult/のファイルが追跡されていないことを確認
git ls-files | grep -E '^(data|result)/' | grep -v '.gitkeep'
# 何も表示されなければOK

# .envが追跡されていないことを確認
git ls-files | grep '.env$'
# .env.exampleのみ表示されればOK
```

### C-4: GitHub公開

```bash
# GitHubでリポジトリ作成後

# リモート追加
git remote add origin https://github.com/yourusername/garmin-performance-analysis.git

# プッシュ
git push -u origin main

# ⚠️ force pushは絶対に使わない（履歴を削除した場合を除く）
```

---

## ✅ 最終確認チェックリスト

公開前に以下をすべて確認してください：

- [ ] データが外部に配置されている
- [ ] .envファイルが正しく設定されている
- [ ] 動作確認テストがすべてpass
- [ ] Git履歴に個人データが含まれていない
- [ ] README.mdが作成されている
- [ ] LICENSEが追加されている
- [ ] .gitignoreが正しく設定されている
- [ ] `git status`で個人データが含まれていない
- [ ] `git ls-files`で個人データが追跡されていない

---

## 🔒 セキュリティノート

**絶対に公開してはいけないもの:**
- 個人の健康データ（体重、心拍数、走行ルート等）
- APIキーや認証情報
- .envファイル

**公開してよいもの:**
- ソースコード
- ドキュメント
- テストコード
- .env.example（サンプル設定ファイル）
- .gitkeep（空ディレクトリマーカー）

---

## 📞 問題が発生した場合

**データが誤って公開された場合:**
1. 即座にリポジトリをprivateに変更
2. Git履歴から削除（BFG使用）
3. Force pushで履歴を上書き
4. GitHubサポートに連絡してキャッシュ削除を依頼

**参考リンク:**
- [GitHub: Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)
- [BFG Repo-Cleaner](https://rtyley.github.io/bfg-repo-cleaner/)
