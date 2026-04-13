# analyze コマンドのリポジトリ並列解析

**Status**: Draft
**Date**: 2026-04-11
**Branch**: `feature/analyze-parallel`

## 背景

現状の `analyze` コマンド (`main.py:188-501`) は `config.repo_paths` を
for ループで 1 つずつ順次処理している。各リポジトリの解析は LLM 呼び出しが
支配的で 1 リポあたり数十秒〜数分かかり、複数リポ構成のプロジェクト
（例: backend + frontend + worker）では解析時間がリポ数に比例して増大する。

LLM 呼び出しは I/O バウンドなので、スレッドベースの並列化でリポ数に対して
ほぼリニアに時間短縮できる余地がある。

## ゴール

- `analyze` でリポジトリ単位の `SourceParser.parse_repo()` を並列実行する
- `--parallel N` / `-j N` CLI オプションで並列度を制御可能にする
- デフォルト並列度は `min(4, len(repos))`（リポ数が少ない時は過剰リソース消費を避ける）
- 既存の `--resume` が並列モードでも正しく機能する
- 1 リポの失敗が他リポの実行を止めない（部分成功を許容）
- 既存の checkpoint ファイルスキーマは変更しない（後方互換）

## 非ゴール

- `SourceParser.parse_repo()` 内部の並列化（ルート/モデル/ページ抽出は直列のまま）
- 画面分析の並列化（単一 frontend リポの処理なので対象外）
- ユースケース抽出の並列化（全リポ統合後の単一処理）
- プロセスベース並列化（`multiprocessing`）
- 非同期 I/O への書き換え（`asyncio`）

## アーキテクチャ

### 実行フロー

```
config.repo_paths
    │
    ▼
┌────────────────────────────────────────┐
│  メインスレッド (prebuild)              │
│  - 全リポの build_context() を           │
│    config.repo_paths 順で実行           │
│  - all_contexts に順序通り格納          │
│  - 並列度決定 (effective_parallel)      │
│  - completed_repos を除外               │
│  - ThreadPoolExecutor に submit         │
└────────────────────────────────────────┘
    │ Future per repo
    ▼
┌────────────────────────────────────────┐
│  ワーカースレッド (N 並列)              │
│  _parse_single_repo(repo_path, parser) │
│    - parser.parse_repo(repo_path)      │
│    - return RepoParseResult            │
│  例外は catch して success=False で返す │
└────────────────────────────────────────┘
    │ as_completed()
    ▼
┌────────────────────────────────────────┐
│  メインスレッド（集約）                 │
│  - 成功: all_routes.extend(...)         │
│          completed_repos.add(...)      │
│          _save_parse_checkpoint(...)   │
│  - 失敗: failed_repos.append(...)       │
│  - console.print で進捗表示             │
└────────────────────────────────────────┘
    │
    ▼
既存フロー（画面分析 → ユースケース抽出）は無変更
```

### なぜ ThreadPoolExecutor か

LLM 呼び出しは subprocess / HTTP で I/O 待ちが支配的。GIL はブロック
中に解放されるので threading で十分な並列効果が得られる。既存の
同期コード (`SourceParser.parse_repo()`) を無改修で流用できる。
asyncio は LLM provider 層の全面改修が必要、multiprocessing は
プロセス間シリアライズのオーバーヘッドと LLM クライアントの共有不可
という欠点がある。

### なぜ as_completed / メインスレッド集約か

共有状態（`all_routes`, `completed_repos`, checkpoint ファイル）への
書き込みをメインスレッドに閉じ込めることで、ロック不要・競合なし・
`console.print` 出力の崩れなしを同時に達成できる。ワーカーは純粋関数
として `RepoParseResult` dataclass を返すだけに徹する。

## インターフェース

### 新規 CLI オプション

`analyze` コマンドと `all` コマンドに以下を追加:

```python
parallel: int = typer.Option(
    0, "--parallel", "-j",
    help="リポジトリ並列度（0=自動: min(4, repo数)、1=直列）"
)
```

### 使用例

```bash
# デフォルト: min(4, len(repos)) で並列
python main.py analyze --repo ./backend --repo ./frontend --repo ./worker

# 並列度を明示
python main.py analyze --repo ./r1 --repo ./r2 --parallel 2

# 直列にフォールバック（デバッグ用）
python main.py analyze --repo ./r1 --repo ./r2 -j 1

# all コマンドからも使える
python main.py all --repo ./r1 --repo ./r2 --parallel 3
```

### 並列度決定ロジック

```python
def _resolve_parallel(parallel: int, repo_count: int) -> int:
    if parallel < 0:
        raise typer.BadParameter("--parallel must be >= 0")
    if parallel == 0:
        return min(4, repo_count) if repo_count > 0 else 1
    return parallel
```

## データ構造

### RepoParseResult（新規）

ワーカーがメインスレッドに返す結果コンテナ。成功・失敗を一律に扱う。

`context` はワーカーで構築せず、メインスレッドで事前に `all_contexts` に
順序通り格納するため、このフィールドには含めない。

```python
@dataclass
class RepoParseResult:
    repo_name: str
    success: bool
    routes: list = field(default_factory=list)
    controllers: list = field(default_factory=list)
    models: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    entity_operations: list = field(default_factory=list)
    error: Optional[str] = None
```

配置先: `analyzer/source_parser.py`（`SourceParser` 近傍、既存 dataclass 群と同じファイル）

### ワーカー関数（新規）

```python
def _parse_single_repo(
    repo_path: Path,
    parser: SourceParser,
) -> RepoParseResult:
    repo_name = repo_path.name
    try:
        result = parser.parse_repo(repo_path)
        return RepoParseResult(
            repo_name=repo_name,
            success=True,
            routes=result["routes"],
            controllers=result["controllers"],
            models=result["models"],
            pages=result["pages"],
            entity_operations=result.get("entity_operations", []),
        )
    except Exception as e:
        return RepoParseResult(
            repo_name=repo_name,
            success=False,
            error=str(e),
        )
```

配置先: `main.py` 内のヘルパー（`_save_parse_checkpoint` の近く）。`SourceParser`
本体には CLI 依存のロジックを持ち込まない。

## main.py の変更範囲

対象は `run_analyze()` 内の以下のブロック（main.py:270-325）のみ:

```python
for repo_path in config.repo_paths:
    repo_name = str(repo_path.name)
    ctx = build_context(repo_path)
    all_contexts.append(ctx)
    if repo_name in completed_repos:
        ...continue
    ...
    result = parser.parse_repo(repo_path)
    ...
    completed_repos.add(repo_name)
    _save_parse_checkpoint(...)
```

変更後の疑似コード:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

# 全リポの context を順序通り prebuild（軽量処理、並列化不要）
for repo_path in config.repo_paths:
    ctx = build_context(repo_path)
    all_contexts.append(ctx)
    if repo_path.name in completed_repos:
        console.print(
            f"  [dim]リポジトリ: {repo_path.name} (チェックポイントからスキップ)[/dim]"
        )

effective_parallel = _resolve_parallel(parallel, len(config.repo_paths))
pending_repos = [
    rp for rp in config.repo_paths
    if rp.name not in completed_repos
]

if pending_repos:
    console.print(
        f"  [並列度 {effective_parallel}] "
        f"{len(pending_repos)} リポジトリを解析中..."
    )

failed_repos: list[tuple[str, str]] = []  # (name, error)

with ThreadPoolExecutor(max_workers=effective_parallel) as executor:
    future_to_repo = {
        executor.submit(_parse_single_repo, rp, parser): rp
        for rp in pending_repos
    }
    for future in as_completed(future_to_repo):
        result = future.result()
        if result.success:
            all_routes.extend(result.routes)
            all_controllers.extend(result.controllers)
            all_models.extend(result.models)
            all_pages.extend(result.pages)
            all_entity_operations.extend(result.entity_operations)
            completed_repos.add(result.repo_name)
            console.print(
                f"  ✓ {result.repo_name}: "
                f"ルート {len(result.routes)} / "
                f"モデル {len(result.models)} / "
                f"ページ {len(result.pages)} / "
                f"エンティティ操作 {len(result.entity_operations)}"
            )
            _save_parse_checkpoint({
                "routes": all_routes, "controllers": all_controllers,
                "models": all_models, "pages": all_pages,
                "entity_operations": all_entity_operations,
                "completed_repos": list(completed_repos), "phase": "parse",
            }, checkpoint_path)
        else:
            failed_repos.append((result.repo_name, result.error))
            console.print(f"  [red]✗ {result.repo_name}: 失敗 - {result.error}[/red]")

if failed_repos:
    console.print(
        f"\n  [green]成功: {len(completed_repos)}/{len(config.repo_paths)}[/green] | "
        f"[red]失敗: {len(failed_repos)}[/red]"
    )
    for name, err in failed_repos:
        console.print(f"  [red]失敗リポ: {name}[/red]")
    console.print(
        "  [yellow]--resume で再実行すると失敗したリポだけ再試行されます[/yellow]"
    )
```

## エラーハンドリング

- **1 リポの例外**: ワーカー内で catch して `success=False` で返す → 他リポは続行
- **失敗リポの再試行**: `completed_repos` に追加しない → 次回 `--resume` で自動再挑戦
- **全リポ失敗**: `len(failed_repos) == len(config.repo_paths)` の場合のみ `typer.Exit(1)`
- **部分失敗**: 警告ログを出しつつ `exit 0`（画面分析・UC 抽出は成功分で継続）
- **不正な `--parallel` 値**: `parallel < 0` は `typer.BadParameter` で即エラー

## 並行安全性の保証

- `SourceParser` は init 時に `_config` と `_llm` を保持するだけで
  `parse_repo()` 呼び出し間で変更される内部状態を持たない（検証済み: `analyzer/source_parser.py:97-98`）
  → 全ワーカーで同一インスタンスを共有して問題なし
- 共有 list (`all_routes` 等) と checkpoint 書き込みはメインスレッドのみが
  触る → ロック不要
- `console.print` はメインスレッドのみ → Rich 出力の競合なし
- `completed_repos` の set 更新もメインスレッドのみ

## テスト

新規: `tests/test_analyze_parallel.py`

1. **`_parse_single_repo` の純粋性**
   - モック `SourceParser.parse_repo` を渡し `RepoParseResult(success=True)` を検証
   - `parse_repo` が例外を投げたとき `success=False`, `error` にメッセージが入ること
   - 共有状態に touch しないこと（引数で受け取ったもの以外に触れない）

2. **`_resolve_parallel` ロジック**
   - `(0, 2)` → `2`
   - `(0, 10)` → `4`
   - `(1, 5)` → `1`
   - `(8, 3)` → `8`
   - `(-1, 5)` → `BadParameter`
   - `(0, 0)` → `1`（空リストでも安全）

3. **`as_completed` 集約の正しさ**
   - 3 リポ中 1 つ失敗するモックで `ThreadPoolExecutor` を実行
   - `all_routes` に成功 2 リポ分が集約される
   - `completed_repos` に失敗リポが含まれない
   - `failed_repos` に失敗リポが 1 件入る

4. **チェックポイント書き込み**
   - N リポ成功で `_save_parse_checkpoint` が N + 1 回呼ばれる
     （各成功時 N 回 + 最終 "parsed" フェーズ 1 回）
   - 失敗リポは checkpoint の `completed_repos` に含まれない

5. **`--resume` 整合性**
   - `completed_repos = {"repo1"}` で `pending_repos` が `repo1` を除外する
   - スキップされた `repo1` の context は事前ループで構築され `all_contexts` に入る

6. **`all_contexts` の順序保証**
   - `config.repo_paths = [r1, r2, r3]` で `r3` が最初に完了しても
     `all_contexts` は `[r1, r2, r3]` の順になっている
   - prebuild loop が `config.repo_paths` 順で動作することを確認

### 回帰テスト

既存の下記が引き続き pass することを確認:
- `tests/test_attach_operations.py`
- `tests/test_crud_analyzer_entity_ops.py`
- `tests/test_entity_operation_parsing.py`

### 非テスト対象

- 実 LLM 呼び出し（E2E 範疇）
- `ThreadPoolExecutor` 自体の挙動（標準ライブラリ信頼）
- 既存直列パスの動作（既存テストに依存）

## 実装順序

1. `RepoParseResult` dataclass を `analyzer/source_parser.py` に追加
2. `main.py` に `_parse_single_repo` と `_resolve_parallel` ヘルパーを追加
3. `run_analyze` の for ループを ThreadPoolExecutor ブロックに置き換え
4. `analyze` / `all` コマンドに `--parallel` オプション追加
5. `tests/test_analyze_parallel.py` 追加
6. 既存テストが通ることを確認
7. 手動 smoke test: 実リポ 2 つで `--parallel 2` を走らせて結果整合性を確認

## リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| LLM provider のスレッドセーフ性が不明 | ワーカー間で状態破壊 | `claude_code_provider` は subprocess 呼び出しで stateless、`anthropic_provider` は HTTP クライアントがスレッドセーフ。smoke test で確認 |
| Rate limit 超過 | 429 エラーで失敗 | デフォルト並列度 4 に抑制。ユーザーは `--parallel 1` で直列に戻せる |
| Rich の出力が混線 | コンソール表示崩れ | `console.print` をメインスレッドに集約して回避 |
| 大量リポでメモリ増大 | OOM | 各リポの結果はメインスレッドで即 extend → ワーカーは即 GC 対象 |

## 後方互換性

- checkpoint スキーマ: 変更なし。既存の `_checkpoint.json` はそのまま読める
- `--parallel` デフォルト `0` は `min(4, len(repos))` に解決されるので、
  1 リポしかない既存ユーザーは挙動変化なし
- 複数リポユーザーはデフォルトで高速化の恩恵を受ける
