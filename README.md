# RDRA Analyzer

**言語・フレームワーク非依存** の RDRA（Relationship-Driven Requirements Analysis）分析ツール。

対象リポジトリの `CLAUDE.md` / `AGENTS.md` をコンテキストとして活用し、
LLM がどんな言語・フレームワークでも動的にソースコードを解析する。
ユースケース・情報モデル・CRUDギャップを自動抽出し、Playwright による E2E テストを AI エージェントで実行する。

## 対応プロジェクト例

- Laravel (PHP) + Next.js (TypeScript)
- Ruby on Rails
- Django / FastAPI (Python)
- Spring Boot (Java / Kotlin)
- Express / Fastify (Node.js)
- Go (Echo / Gin / Chi)
- Rust (Actix / Axum)
- その他、`CLAUDE.md` があればどんなプロジェクトでも対応可能

## 機能

| ステップ | コマンド | 機能 | 出力形式 |
|----------|---------|------|---------|
| **1** | `analyze` | ソースコード解析 → 画面分析 → ユースケース抽出 | JSON |
| **2** | `verify` | シナリオ×画面 突き合わせ検証 | JSON/Markdown |
| **3** | `scenarios` | 操作シナリオ生成 | JSON |
| **4** | `rdra` | RDRAモデル生成（情報モデル・ユースケース複合図・アクティビティ図） | Mermaid/Markdown |
| **5** | `viewer` | インタラクティブビューワー起動 | HTML |
| - | `gap` | CRUDギャップ分析 | Markdownテーブル |
| - | `e2e` | E2Eテスト自動実行（エージェントループ付き） | JSON/Markdown/スクリーンショット |

## 仕組み

```
[対象リポジトリ]
    |
    +-- CLAUDE.md / AGENTS.md  --> [プロジェクトコンテキスト構築]
    +-- README.md                       |
    +-- package.json 等                 v
    +-- ディレクトリ構造         [LLM が動的にコード構造を抽出]
                                        |
                               +--------+--------+
                               v        v        v
                          ルート抽出  モデル抽出  ページ抽出
                               |        |        |
                               v        v        v
                          [画面分析] --> [UC抽出] --> [シナリオ生成]
                               |             |             |
                               v             v             v
                          [検証] --> [RDRA] --> [ビューワー]
```

`CLAUDE.md` / `AGENTS.md` にプロジェクトの構造・規約・技術スタックが記載されていれば、
LLM はそれをコンテキストとして使い、適切なファイルを探索してルート・モデル・ビューを抽出する。

## ファイル構成

```
rdra-analyzer/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example              # 環境変数サンプル
├── config.py                 # 設定・環境変数管理
├── main.py                   # CLI エントリーポイント（Typer）
├── llm/
│   ├── __init__.py           # プロバイダーファクトリー
│   ├── provider.py           # LLMProvider 抽象クラス
│   ├── anthropic_provider.py # Anthropic API 実装
│   └── claude_code_provider.py  # Claude Code CLI 実装
├── analyzer/
│   ├── __init__.py
│   ├── project_context.py    # CLAUDE.md / AGENTS.md コンテキスト構築
│   ├── source_parser.py      # LLM 駆動の汎用ソースコード解析
│   ├── screen_analyzer.py    # 画面分析（UI要素・レイアウト・ナビゲーション抽出）
│   ├── usecase_extractor.py  # LLM でユースケース抽出（画面仕様活用）
│   ├── scenario_builder.py   # 操作シナリオ構造化
│   └── scenario_verifier.py  # シナリオ×画面 突き合わせ検証
├── rdra/
│   ├── __init__.py
│   ├── information_model.py  # 情報モデル生成
│   ├── usecase_diagram.py    # ユースケース複合図生成
│   ├── activity_diagram.py   # アクティビティ図生成
│   └── mermaid_renderer.py   # Mermaid 記法出力
├── gap/
│   ├── __init__.py
│   └── crud_analyzer.py      # CRUD ギャップ分析
└── e2e/
    ├── __init__.py
    ├── playwright_runner.py   # Playwright 実行エンジン
    ├── agent_loop.py          # エージェントループ（エラー時リカバリー）
    └── scenario_executor.py  # シナリオ実行管理
```

## セットアップ

### 1. Python 環境の準備（Python 3.11 以上が必要）

```bash
# Python 3.11 以上を確認（macOS の場合 Homebrew でインストール）
python3 --version  # 3.11 以上であること
# macOS で 3.9/3.10 の場合:
#   brew install python@3.11

# 仮想環境を作成（Python 3.11 以上を明示的に指定）
python3.11 -m venv .venv   # または python3.12, python3.13 など
# Homebrew の場合: /opt/homebrew/bin/python3.11 -m venv .venv

# 仮想環境を有効化
source .venv/bin/activate   # macOS/Linux
# .venv\Scripts\activate   # Windows

# 依存パッケージをインストール
pip install -r requirements.txt

# Playwright ブラウザをインストール（E2E テストを使う場合）
playwright install chromium
```

> **注意**: macOS のシステム Python (`/usr/bin/python3`) は 3.9 で要件を満たしません。
> Homebrew 等で Python 3.11 以上をインストールしてください。

### 2. 環境変数の設定

```bash
cp .env.example .env
```

`.env` を編集:

```env
# LLMプロバイダー選択
# Anthropic API を使う場合（デフォルト）:
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx

# Claude Code CLI を使う場合（ローカル実行・APIキー不要）:
USE_CLAUDE_CODE=true

# 解析対象リポジトリのパス（カンマ区切りで複数指定可）
REPO_PATHS=/path/to/your/project
# REPO_PATHS=/path/to/backend,/path/to/frontend

# E2E テスト対象 URL
E2E_BASE_URL=http://localhost:3000
```

### 3. 対象リポジトリの準備

解析対象リポジトリに `CLAUDE.md` を配置することを推奨:

```markdown
# プロジェクト名

## 技術スタック
- バックエンド: Rails 7 (Ruby 3.2)
- フロントエンド: React + Vite
- DB: PostgreSQL

## ディレクトリ構成
- app/controllers/ - コントローラー
- app/models/ - モデル
- config/routes.rb - ルーティング
- frontend/src/pages/ - フロントエンドページ
```

`CLAUDE.md` がなくても、`README.md` やマニフェストファイル（`package.json` 等）から技術スタックを自動検出する。

## 実行方法

以下のコマンドは仮想環境を有効化した状態（`source .venv/bin/activate`）で実行してください。
未有効化の場合は `.venv/bin/python main.py ...` のように明示的にパスを指定できます。

### 設定確認

```bash
python main.py config --repo /path/to/project
```

### 推奨実行フロー

```bash
# 1. ソースコード解析 → 画面分析 → ユースケース抽出
python main.py analyze --repo /path/to/backend --repo /path/to/frontend

# 2. シナリオ×画面 突き合わせ検証
python main.py verify                       # 検証のみ
python main.py verify --fix                 # 検証 + LLMで自動修正

# 3. シナリオ生成（画面仕様に基づいて生成）
python main.py scenarios --max 10           # 10件ずつ生成
python main.py scenarios --offset 10        # 続きから再開

# 4. RDRAモデル生成
python main.py rdra --repo /path/to/backend --repo /path/to/frontend

# 5. ビューワー起動
python main.py viewer --regenerate
```

> 中断しても各ステップで中間保存されているため、`--resume`（analyze）や `--offset`（scenarios）で再開可能。

### 個別コマンド詳細

#### analyze: ソースコード解析・画面分析・ユースケース抽出

ソースコード解析 → 画面分析（UI要素抽出） → ユースケース抽出を一括実行する。
画面分析結果はユースケース抽出時のコンテキストとして活用される。

```bash
python main.py analyze --repo /path/to/backend --repo /path/to/frontend

# オプション
--skip-llm              # LLM呼び出しをスキップ（最低限の解析のみ）
--max-routes 50         # 解析ルート数を制限
--batch-size 5          # 画面分析の1バッチあたりのページ数（デフォルト5）
--resume                # 前回の中断箇所から再開（解析済み画面仕様も再利用）
--checkpoint-interval 30  # 中間保存の間隔（デフォルト30件）
```

出力: `./output/usecases/analysis_result.json`, `./output/usecases/ui.yml`, `./output/usecases/_checkpoint.json`

#### scenarios: シナリオ生成

ユースケースから操作シナリオを生成する。`ui.yml` が存在すれば自動的に画面仕様を参照し、実際のUI要素に基づいたステップを生成する。
生成後に画面仕様との突き合わせ検証を行い、不整合があれば自動的に再生成する。

```bash
python main.py scenarios                    # 先頭5件から生成
python main.py scenarios --max 10           # 10件ずつ生成
python main.py scenarios --offset 10        # 11件目から再開
```

出力: `./output/usecases/analysis_result.json`（scenarios フィールドに追加）

#### verify: シナリオ×画面 突き合わせ検証

操作シナリオの各ステップが実際の画面UI要素と整合しているか検証する。

```bash
python main.py verify             # 検証のみ（レポート出力）
python main.py verify --fix       # 検証 + LLMで不整合シナリオを自動修正
```

出力:

| ファイル | 内容 |
|---------|------|
| `./output/usecases/verification_report.json` | 検証結果（JSON） |
| `./output/usecases/verification_report.md` | 検証結果（Markdown） |

#### rdra: RDRAモデル生成

情報モデル・ユースケース複合図・状態遷移図・ビジネスポリシー・ビューワーを生成する。
`analyze` で保存されたチェックポイントからモデル・ルート・コントローラーを読み込むため、リポジトリの再解析は不要。

```bash
python main.py rdra
```

出力: `./output/rdra/` 配下に Markdown + `viewer.html`

#### viewer: ビューワー起動

```bash
python main.py viewer --regenerate          # ビューワーを再生成して起動
python main.py viewer                       # 既存のviewer.htmlで起動
python main.py viewer --port 3000           # ポート指定
```

ビューワーの機能:
- 情報モデル（ER図 / ユースケース単位グループ化）
- ユースケース複合図・条件図（クリックで詳細パネル表示）
- 操作シナリオ（シーケンス図をサイドパネルで表示）
- 状態遷移図・ビジネスポリシー（IDクリックで詳細パネル、コード参照箇所を表示）
- 画面一覧（ボタン・フォーム・遷移先等の詳細表示）
- アクター・エンティティ×UC CRUDマトリクス
- 全ダイアグラムのズーム・パン操作
- エンティティ名・UC-ID・アクター名・BP-IDのクロスリファレンスクリック

#### gap: CRUDギャップ分析

`analyze` のチェックポイントからルート・モデルを読み込んで分析する。

```bash
python main.py gap
```

#### e2e: E2Eテスト実行

操作シナリオを Playwright (Chromium) で自動実行する。

```bash
python main.py e2e                          # 全シナリオ実行（ヘッドレス）
python main.py e2e --no-headless            # ブラウザ表示あり
python main.py e2e --filter UC-001          # 特定ユースケースのみ
python main.py e2e --normal-only            # 正常系のみ
```

`.env` の E2E 関連設定:

```env
E2E_BASE_URL=http://localhost:3000
E2E_TEST_EMAIL=test@example.com
E2E_TEST_PASSWORD=password
E2E_HEADLESS=true
E2E_TIMEOUT_MS=30000
E2E_MAX_RETRIES=3
```

> **注意**: ログインは1ユーザー分のみ対応。アクター切り替えやテストデータの事前投入は手動で準備が必要。

#### all: 全パート一括実行

### 全パートを一括実行

```bash
python main.py all --repo /path/to/project
python main.py all --repo /path/to/project --skip-e2e
```

## LLMプロバイダーの切り替え

| 環境変数 | プロバイダー | 用途 |
|---------|------------|------|
| `USE_CLAUDE_CODE=false`（デフォルト） | Anthropic API | 本番・CI/CD |
| `USE_CLAUDE_CODE=true` | Claude Code CLI | ローカル開発（APIキー不要） |

## 設計のポイント

### 動的解析（analyzer/）
- `CLAUDE.md` / `AGENTS.md` をプロジェクトコンテキストとして活用
- Claude Code CLI の `analyze_codebase` で対象リポジトリを自律探索
- マニフェストファイル（`package.json`, `composer.json` 等）から技術スタックを自動検出
- LLM に言語固有の解析を動的に指示（ハードコード不要）

### RDRAモデル（rdra/）
- Mermaid ER図にエンティティの属性・リレーションを自動マッピング
- LLM でモデル名の日本語化・リレーション種別を推定
- カテゴリ別サブグラフによるユースケース複合図

### CRUDギャップ（gap/）
- HTTP メソッド（POST/GET/PUT/DELETE）からCRUD操作を自動判定
- 操作シナリオのテキストからもCRUD操作を検出
- エンティティ名の複数形・ケバブケース・スネークケースに対応

### E2E（e2e/）
- Playwright による全シナリオ自動実行
- エラー時に LLM でリカバリーアクションを決定
- 認証エラー・要素未検出・タイムアウトなど複数のリカバリーパターン

## トラブルシューティング

### Playwright のタイムアウトエラー

`.env` で `E2E_TIMEOUT_MS` を増やす:

```env
E2E_TIMEOUT_MS=60000  # 60秒
```

### Claude Code CLI の認証エラー

```bash
claude auth login
```

## ライセンス

MIT
