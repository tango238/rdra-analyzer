# analyze コマンド リポジトリ並列解析 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `analyze` コマンド内でリポジトリ単位の `SourceParser.parse_repo()` を `ThreadPoolExecutor` で並列化し、`--parallel/-j N` で並列度を制御可能にする。

**Architecture:** `run_analyze` の順次 for ループを 3 つの小さな helper (`_resolve_parallel`, `_parse_single_repo`, `_run_parallel_parse`) に分解する。ワーカーは純粋関数として `RepoParseResult` を返すだけにし、共有状態への書き込みは `as_completed` のコールバック経由でメインスレッドに集約してロック不要にする。context は並列実行前に `config.repo_paths` 順で prebuild して順序を保証する。

**Tech Stack:** Python 3.11+, `concurrent.futures.ThreadPoolExecutor`, Typer (CLI), Rich (console), pytest, dataclasses

**Reference Spec:** `docs/superpowers/specs/2026-04-11-analyze-parallel-design.md`

---

## File Structure

**Create:**
- `tests/test_analyze_parallel.py` — 新規テストファイル。`_resolve_parallel`, `_parse_single_repo`, `_run_parallel_parse` の単体テスト

**Modify:**
- `analyzer/source_parser.py` — `RepoParseResult` dataclass を追加（既存の `ParsedRoute` 等の dataclass 群の近く）
- `main.py` — `_resolve_parallel`, `_parse_single_repo`, `_run_parallel_parse` の helper を追加、`run_analyze` の for ループを並列版に置き換え、`analyze` / `all` コマンドに `--parallel` オプション追加

---

## Task 1: Add `RepoParseResult` dataclass

**Files:**
- Modify: `analyzer/source_parser.py` (dataclass 定義群の末尾に追記)
- Test: `tests/test_analyze_parallel.py` (新規)

- [ ] **Step 1: Create test file with RepoParseResult dataclass test**

Create `tests/test_analyze_parallel.py` with:

```python
"""リポジトリ並列解析ヘルパーの単体テスト"""
import pytest
from analyzer.source_parser import RepoParseResult


class TestRepoParseResult:
    def test_success_result_has_empty_lists_by_default(self):
        result = RepoParseResult(repo_name="r1", success=True)
        assert result.repo_name == "r1"
        assert result.success is True
        assert result.routes == []
        assert result.controllers == []
        assert result.models == []
        assert result.pages == []
        assert result.entity_operations == []
        assert result.error is None

    def test_failure_result_carries_error_message(self):
        result = RepoParseResult(
            repo_name="bad", success=False, error="LLM timeout"
        )
        assert result.success is False
        assert result.error == "LLM timeout"
        assert result.routes == []

    def test_default_lists_are_independent_between_instances(self):
        """field(default_factory=list) が正しく使われていることの検証"""
        a = RepoParseResult(repo_name="a", success=True)
        b = RepoParseResult(repo_name="b", success=True)
        a.routes.append("x")
        assert b.routes == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyze_parallel.py::TestRepoParseResult -v`
Expected: FAIL with `ImportError: cannot import name 'RepoParseResult' from 'analyzer.source_parser'`

- [ ] **Step 3: Add RepoParseResult dataclass**

Append to `analyzer/source_parser.py` (after the existing `EntityOperation` dataclass, before `class SourceParser`):

```python
@dataclass
class RepoParseResult:
    """
    並列解析ワーカーがメインスレッドに返す結果コンテナ。

    成功・失敗を同一の型で扱うことで、Future.result() の呼び出し側が
    例外ハンドリングを個別に書かなくて済む。context は並列処理の外で
    prebuild するため、このクラスには含めない。
    """
    repo_name: str
    success: bool
    routes: list = field(default_factory=list)
    controllers: list = field(default_factory=list)
    models: list = field(default_factory=list)
    pages: list = field(default_factory=list)
    entity_operations: list = field(default_factory=list)
    error: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyze_parallel.py::TestRepoParseResult -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add analyzer/source_parser.py tests/test_analyze_parallel.py
git commit -m "feat: add RepoParseResult dataclass for parallel parse workers"
```

---

## Task 2: Add `_resolve_parallel` helper

**Files:**
- Modify: `main.py` (helper 関数群、`_save_parse_checkpoint` の近く)
- Test: `tests/test_analyze_parallel.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analyze_parallel.py`:

```python
import typer
from main import _resolve_parallel


class TestResolveParallel:
    def test_zero_with_two_repos_returns_two(self):
        assert _resolve_parallel(0, 2) == 2

    def test_zero_with_many_repos_caps_at_four(self):
        assert _resolve_parallel(0, 10) == 4

    def test_zero_with_one_repo_returns_one(self):
        assert _resolve_parallel(0, 1) == 1

    def test_explicit_one_returns_one(self):
        assert _resolve_parallel(1, 5) == 1

    def test_explicit_exceeds_repos_preserved(self):
        assert _resolve_parallel(8, 3) == 8

    def test_negative_raises_bad_parameter(self):
        with pytest.raises(typer.BadParameter):
            _resolve_parallel(-1, 5)

    def test_zero_with_empty_returns_one(self):
        assert _resolve_parallel(0, 0) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyze_parallel.py::TestResolveParallel -v`
Expected: FAIL with `ImportError: cannot import name '_resolve_parallel' from 'main'`

- [ ] **Step 3: Add the helper to main.py**

Insert in `main.py` directly after the `_load_parse_checkpoint` function (around line 186):

```python
def _resolve_parallel(parallel: int, repo_count: int) -> int:
    """
    CLI `--parallel` 値を実行時の並列度に解決する。

    Args:
        parallel: CLI 引数値。0 は自動、1 以上はそのまま、負数はエラー。
        repo_count: 対象リポジトリ数。

    Returns:
        実際に ThreadPoolExecutor に渡す max_workers 値。
        repo_count が 0 の場合でも安全な値（1）を返す。

    Raises:
        typer.BadParameter: parallel が負の値のとき。
    """
    if parallel < 0:
        raise typer.BadParameter("--parallel must be >= 0")
    if parallel == 0:
        return min(4, repo_count) if repo_count > 0 else 1
    return parallel
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyze_parallel.py::TestResolveParallel -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_analyze_parallel.py
git commit -m "feat: add _resolve_parallel helper for CLI parallelism"
```

---

## Task 3: Add `_parse_single_repo` worker function

**Files:**
- Modify: `main.py`
- Test: `tests/test_analyze_parallel.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analyze_parallel.py`:

```python
from unittest.mock import MagicMock
from main import _parse_single_repo


class TestParseSingleRepo:
    def test_success_returns_populated_result(self, tmp_path):
        repo = tmp_path / "repo1"
        repo.mkdir()
        parser = MagicMock()
        parser.parse_repo.return_value = {
            "routes": ["r1", "r2"],
            "controllers": ["c1"],
            "models": ["m1"],
            "pages": [],
            "entity_operations": ["eo1"],
        }

        result = _parse_single_repo(repo, parser)

        assert result.success is True
        assert result.repo_name == "repo1"
        assert result.routes == ["r1", "r2"]
        assert result.controllers == ["c1"]
        assert result.models == ["m1"]
        assert result.pages == []
        assert result.entity_operations == ["eo1"]
        assert result.error is None
        parser.parse_repo.assert_called_once_with(repo)

    def test_failure_captures_exception_message(self, tmp_path):
        repo = tmp_path / "bad"
        repo.mkdir()
        parser = MagicMock()
        parser.parse_repo.side_effect = RuntimeError("LLM timeout after 120s")

        result = _parse_single_repo(repo, parser)

        assert result.success is False
        assert result.repo_name == "bad"
        assert result.error == "LLM timeout after 120s"
        assert result.routes == []
        assert result.models == []

    def test_missing_entity_operations_defaults_to_empty(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        parser = MagicMock()
        parser.parse_repo.return_value = {
            "routes": [],
            "controllers": [],
            "models": [],
            "pages": [],
            # entity_operations キーが無い古い戻り値形
        }

        result = _parse_single_repo(repo, parser)

        assert result.success is True
        assert result.entity_operations == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyze_parallel.py::TestParseSingleRepo -v`
Expected: FAIL with `ImportError: cannot import name '_parse_single_repo' from 'main'`

- [ ] **Step 3: Add the worker function to main.py**

Add to `main.py` directly after `_resolve_parallel` (from Task 2):

```python
def _parse_single_repo(repo_path: Path, parser) -> "RepoParseResult":
    """
    並列ワーカー: 1 リポジトリを解析し RepoParseResult を返す。

    例外は catch して success=False で包んで返すので、呼び出し側は
    Future.result() を例外ハンドリングなしで受け取れる。

    ここでは build_context() を呼ばない。context は並列実行の外で
    config.repo_paths 順に事前構築する必要があるため。
    （parse_repo 内部では独自に build_context を呼ぶがそれは LLM プロンプト用）
    """
    from analyzer.source_parser import RepoParseResult

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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyze_parallel.py::TestParseSingleRepo -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add main.py tests/test_analyze_parallel.py
git commit -m "feat: add _parse_single_repo worker for parallel parse"
```

---

## Task 4: Add `_run_parallel_parse` orchestrator

**Files:**
- Modify: `main.py`
- Test: `tests/test_analyze_parallel.py`

The orchestrator accepts an `on_complete` callback that fires on the main thread
for each finished future, so the caller (run_analyze) can perform aggregation,
checkpoint saving, and console printing in completion order.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_analyze_parallel.py`:

```python
from main import _run_parallel_parse


class TestRunParallelParse:
    def _make_parser(self, per_repo_fn):
        """per_repo_fn: (repo_path) -> dict または raises"""
        parser = MagicMock()
        parser.parse_repo.side_effect = per_repo_fn
        return parser

    def test_all_successes_returned_as_list(self, tmp_path):
        repos = []
        for name in ["r1", "r2", "r3"]:
            p = tmp_path / name
            p.mkdir()
            repos.append(p)

        def fake_parse(rp):
            return {
                "routes": [f"{rp.name}-route"],
                "controllers": [],
                "models": [f"{rp.name}-model"],
                "pages": [],
                "entity_operations": [],
            }
        parser = self._make_parser(fake_parse)

        successes, failures = _run_parallel_parse(
            pending_repos=repos, parser=parser, parallel=2,
        )

        assert len(successes) == 3
        assert len(failures) == 0
        names = {r.repo_name for r in successes}
        assert names == {"r1", "r2", "r3"}

    def test_mixed_success_and_failure_partitioned(self, tmp_path):
        repos = []
        for name in ["good1", "bad", "good2"]:
            p = tmp_path / name
            p.mkdir()
            repos.append(p)

        def fake_parse(rp):
            if rp.name == "bad":
                raise ValueError("boom")
            return {
                "routes": [], "controllers": [], "models": [],
                "pages": [], "entity_operations": [],
            }
        parser = self._make_parser(fake_parse)

        successes, failures = _run_parallel_parse(
            pending_repos=repos, parser=parser, parallel=2,
        )

        assert len(successes) == 2
        assert len(failures) == 1
        assert failures[0].repo_name == "bad"
        assert "boom" in failures[0].error
        success_names = {r.repo_name for r in successes}
        assert success_names == {"good1", "good2"}

    def test_on_complete_fires_for_every_result(self, tmp_path):
        repos = []
        for name in ["a", "b", "c"]:
            p = tmp_path / name
            p.mkdir()
            repos.append(p)

        def fake_parse(rp):
            if rp.name == "b":
                raise RuntimeError("fail")
            return {
                "routes": [], "controllers": [], "models": [],
                "pages": [], "entity_operations": [],
            }
        parser = self._make_parser(fake_parse)

        seen = []
        def on_complete(result):
            seen.append((result.repo_name, result.success))

        _run_parallel_parse(
            pending_repos=repos, parser=parser, parallel=2,
            on_complete=on_complete,
        )

        assert len(seen) == 3
        seen_by_name = dict(seen)
        assert seen_by_name["a"] is True
        assert seen_by_name["b"] is False
        assert seen_by_name["c"] is True

    def test_empty_pending_repos_returns_empty(self, tmp_path):
        parser = MagicMock()
        successes, failures = _run_parallel_parse(
            pending_repos=[], parser=parser, parallel=4,
        )
        assert successes == []
        assert failures == []
        parser.parse_repo.assert_not_called()

    def test_parallel_one_runs_serially(self, tmp_path):
        repos = [tmp_path / f"r{i}" for i in range(3)]
        for r in repos:
            r.mkdir()
        parser = self._make_parser(lambda rp: {
            "routes": [], "controllers": [], "models": [],
            "pages": [], "entity_operations": [],
        })

        successes, failures = _run_parallel_parse(
            pending_repos=repos, parser=parser, parallel=1,
        )

        assert len(successes) == 3
        assert len(failures) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_analyze_parallel.py::TestRunParallelParse -v`
Expected: FAIL with `ImportError: cannot import name '_run_parallel_parse' from 'main'`

- [ ] **Step 3: Add the orchestrator to main.py**

Add the following import near the top of `main.py` (with other stdlib imports, after `import sys`):

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable
```

Then add the orchestrator function to `main.py` directly after `_parse_single_repo` (from Task 3):

```python
def _run_parallel_parse(
    pending_repos: list[Path],
    parser,
    parallel: int,
    on_complete: Optional[Callable] = None,
) -> tuple[list, list]:
    """
    pending_repos を ThreadPoolExecutor で並列に parse する。

    共有状態（all_routes, completed_repos, checkpoint ファイル等）の更新は
    呼び出し側の責務。このヘルパーは結果を (successes, failures) に分ける
    だけで、on_complete コールバック経由で呼び出し側にメインスレッドで
    1 件ずつ通知する（as_completed の順序 = 完了順）。

    Args:
        pending_repos: 解析対象のリポジトリパス一覧（completed_repos を除外済み）
        parser: SourceParser インスタンス（全ワーカーで共有される）
        parallel: max_workers（_resolve_parallel で解決済みの値）
        on_complete: 各 Future 完了時にメインスレッドで呼ばれる callback。
                     シグネチャ: (RepoParseResult) -> None

    Returns:
        (successes, failures) の 2 タプル。各要素は RepoParseResult のリスト。
    """
    successes: list = []
    failures: list = []

    if not pending_repos:
        return successes, failures

    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = [
            executor.submit(_parse_single_repo, rp, parser)
            for rp in pending_repos
        ]
        for future in as_completed(futures):
            result = future.result()
            if on_complete is not None:
                on_complete(result)
            if result.success:
                successes.append(result)
            else:
                failures.append(result)

    return successes, failures
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_analyze_parallel.py::TestRunParallelParse -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Run the full new test file to verify nothing regressed**

Run: `python -m pytest tests/test_analyze_parallel.py -v`
Expected: PASS (18 tests total: 3+7+3+5)

- [ ] **Step 6: Commit**

```bash
git add main.py tests/test_analyze_parallel.py
git commit -m "feat: add _run_parallel_parse orchestrator with as_completed callback"
```

---

## Task 5: Refactor `run_analyze` to use parallel helpers + add `--parallel` option

**Files:**
- Modify: `main.py` (`run_analyze` function, lines ~188-325)

This task replaces the sequential `for repo_path in config.repo_paths:` block
with a context prebuild loop followed by a `_run_parallel_parse` call whose
`on_complete` callback performs the existing aggregation/checkpoint/print logic.

- [ ] **Step 1: Add `--parallel` option to `run_analyze` signature**

In `main.py`, locate the `run_analyze` signature (currently ends around line 210
with `batch_size: int = typer.Option(...)`) and add a new parameter just before
the closing `):`:

```python
    parallel: int = typer.Option(
        0, "--parallel", "-j",
        help="リポジトリ並列度（0=自動: min(4, リポ数)、1=直列）"
    ),
```

- [ ] **Step 2: Replace the sequential for-loop with parallel version**

Locate the block in `run_analyze` starting with:

```python
    for repo_path in config.repo_paths:
        repo_name = str(repo_path.name)

        # コンテキストは常に構築（再開時も必要）
        ctx = build_context(repo_path)
        all_contexts.append(ctx)
```

and ending with:

```python
        # リポジトリごとにチェックポイント保存
        _save_parse_checkpoint({
            "routes": all_routes, "controllers": all_controllers,
            "models": all_models, "pages": all_pages,
            "entity_operations": all_entity_operations,
            "completed_repos": list(completed_repos), "phase": "parse",
        }, checkpoint_path)
        console.print(f"    [dim]-> チェックポイント保存: {checkpoint_path}[/dim]")
```

Replace that entire block with:

```python
    # 全リポの context を順序通り prebuild（軽量処理、並列化不要）
    for repo_path in config.repo_paths:
        ctx = build_context(repo_path)
        all_contexts.append(ctx)
        repo_name = repo_path.name
        if repo_name in completed_repos:
            console.print(
                f"  [dim]リポジトリ: {repo_name} (チェックポイントからスキップ)[/dim]"
            )
            continue
        console.print(f"  [bold]リポジトリ: {repo_name}[/bold]")
        for ctx_file in ["CLAUDE.md", "AGENTS.md"]:
            if (repo_path / ctx_file).exists():
                console.print(f"    [dim]{ctx_file} を検出[/dim]")
        if ctx.detected_stacks:
            console.print(f"    [dim]技術スタック: {', '.join(ctx.detected_stacks)}[/dim]")

    pending_repos = [
        rp for rp in config.repo_paths
        if rp.name not in completed_repos
    ]

    effective_parallel = _resolve_parallel(parallel, len(config.repo_paths))
    failed_repos: list[tuple[str, str]] = []

    if pending_repos:
        console.print(
            f"\n  [並列度 {effective_parallel}] "
            f"{len(pending_repos)} リポジトリを解析中..."
        )

        def _on_repo_complete(result):
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
                console.print(
                    f"  [red]✗ {result.repo_name}: 失敗 - {result.error}[/red]"
                )

        _run_parallel_parse(
            pending_repos=pending_repos,
            parser=parser,
            parallel=effective_parallel,
            on_complete=_on_repo_complete,
        )

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
        if len(failed_repos) == len(pending_repos) and pending_repos:
            raise typer.Exit(1)
```

- [ ] **Step 3: Verify imports at the top of main.py include the new names**

Confirm `main.py` has these imports near the top (add any that are missing):

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional
```

(`Optional` is already imported. `Callable`, `ThreadPoolExecutor`, `as_completed`
were added in Task 4. Verify they exist.)

- [ ] **Step 4: Verify prebuild ordering by code inspection**

The spec requires `all_contexts` to be populated in `config.repo_paths` order
regardless of parallel completion order. This is guaranteed by construction:
the prebuild loop at the top of the block iterates `config.repo_paths` directly
and appends to `all_contexts` in order, before any parallel execution starts.
Read the prebuild loop you just wrote and confirm no `completed_repos` branch
skips the `all_contexts.append(ctx)` call — the append must happen for every
repo. (Spec test #6 is satisfied by this structural guarantee rather than a
standalone unit test.)

- [ ] **Step 5: Run the new test file to confirm helpers still work**

Run: `python -m pytest tests/test_analyze_parallel.py -v`
Expected: PASS (18 tests)

- [ ] **Step 6: Run the full existing test suite to check for regressions**

Run: `python -m pytest tests/ -v`
Expected: All existing tests pass plus the 18 new tests. No failures.

- [ ] **Step 7: Smoke test the CLI help**

Run: `python main.py analyze --help`
Expected: `--parallel` / `-j` option appears in the output with the Japanese help text.

- [ ] **Step 8: Commit**

```bash
git add main.py
git commit -m "feat: parallelize per-repo parse_repo in analyze command

Extract the sequential for-loop over config.repo_paths into a prebuild
pass (for context ordering) plus a ThreadPoolExecutor-backed parallel
parse via _run_parallel_parse. Aggregation, checkpoint saving, and
console output happen on the main thread via on_complete callback.

Add --parallel/-j option (default 0 = min(4, repo_count))."
```

---

## Task 6: Propagate `--parallel` to `all` command

**Files:**
- Modify: `main.py` (`run_all` function, around line 1364)

- [ ] **Step 1: Add `--parallel` option to `run_all` signature**

In `main.py`, locate `run_all` (starts around line 1364). Add the parallel
option right after `base_url`:

```python
    parallel: int = typer.Option(
        0, "--parallel", "-j",
        help="リポジトリ並列度（0=自動: min(4, リポ数)、1=直列）"
    ),
```

- [ ] **Step 2: Pass `parallel` through to `run_analyze.callback`**

In `run_all`, locate the `run_analyze.callback(...)` call (around line 1402) and
add `parallel=parallel` to the keyword arguments:

```python
    result = run_analyze.callback(
        repo=repo,
        output_dir=output_dir,
        max_routes=200,
        skip_llm=False,
        parallel=parallel,
    )
```

- [ ] **Step 3: Verify analyze.callback accepts the parameter**

Because `run_analyze` also defines other parameters with defaults (`resume`,
`checkpoint_interval`, `batch_size`) that `run_all` doesn't pass, Typer will
use their defaults. Confirm this is still true by reading the signature of
`run_analyze` after Task 5 and ensuring `parallel` has a default of `0`.

Run: `python main.py all --help`
Expected: `--parallel` / `-j` option appears.

- [ ] **Step 4: Smoke test the CLI**

Run: `python main.py all --help`
Expected: output includes `--parallel` / `-j` with Japanese help.

Run: `python main.py analyze --parallel -1 --repo /tmp/nonexistent 2>&1 | head -5`
Expected: error message containing "must be >= 0" and non-zero exit.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: propagate --parallel option to 'all' command"
```

---

## Task 7: Manual smoke test with real repositories

**Files:** No code changes. Verification only.

This is a hand-run smoke test to confirm real LLM calls work across multiple
worker threads. The prior tasks only verified the helpers with mocks.

- [ ] **Step 1: Identify two test repositories**

Pick two small repositories (e.g., two small Laravel or Node projects) that have
`CLAUDE.md` or at least `package.json` / `composer.json` to trigger source
parsing. Note their absolute paths.

- [ ] **Step 2: Run analyze with --parallel 1 (serial baseline)**

Run:
```bash
rm -rf /tmp/rdra-smoke-serial
python main.py analyze \
  --repo /path/to/repo1 \
  --repo /path/to/repo2 \
  --output /tmp/rdra-smoke-serial \
  --parallel 1
```
Expected:
- `[並列度 1] 2 リポジトリを解析中...` is printed
- Both repos complete and produce `/tmp/rdra-smoke-serial/usecases/analysis_result.json`
- Exit code 0

- [ ] **Step 3: Run analyze with --parallel 2 (parallel)**

Run:
```bash
rm -rf /tmp/rdra-smoke-parallel
python main.py analyze \
  --repo /path/to/repo1 \
  --repo /path/to/repo2 \
  --output /tmp/rdra-smoke-parallel \
  --parallel 2
```
Expected:
- `[並列度 2] 2 リポジトリを解析中...` is printed
- Both repos complete (possibly in different order than they were passed)
- `/tmp/rdra-smoke-parallel/usecases/analysis_result.json` exists
- Wall-clock time is noticeably shorter than the serial run
- Exit code 0

- [ ] **Step 4: Compare outputs**

Run:
```bash
diff <(jq -S .usecases /tmp/rdra-smoke-serial/usecases/analysis_result.json) \
     <(jq -S .usecases /tmp/rdra-smoke-parallel/usecases/analysis_result.json)
```
Expected: No diff, OR differences limited to LLM non-determinism (ordering of
entries within lists, minor wording variations). Structural consistency
(same number of routes/models/pages per repo) must match.

Note: Exact match is not required because LLM responses vary between runs, but
the repo counts and structural shape should be equivalent.

- [ ] **Step 5: Test --resume in parallel mode**

Run parallel mode, then interrupt it with Ctrl+C midway (if possible), then:
```bash
python main.py analyze \
  --repo /path/to/repo1 \
  --repo /path/to/repo2 \
  --output /tmp/rdra-smoke-parallel \
  --parallel 2 \
  --resume
```
Expected: any repos already in `_checkpoint.json`'s `completed_repos` are
skipped with "チェックポイントからスキップ"; remaining repos are parsed in parallel.

- [ ] **Step 6: Test failure path**

Run:
```bash
rm -rf /tmp/rdra-smoke-fail
python main.py analyze \
  --repo /path/to/repo1 \
  --repo /tmp/nonexistent-repo \
  --output /tmp/rdra-smoke-fail \
  --parallel 2
```
Expected:
- `repo1` shows `✓` with stats
- `/tmp/nonexistent-repo` shows `✗` with error message
- Summary shows "成功: 1/2 | 失敗: 1"
- "失敗リポ: nonexistent-repo" printed
- "--resume で再実行..." hint printed
- Exit code is 0 (partial success) because `repo1` succeeded

- [ ] **Step 7: Document results**

If all smoke tests pass, no further commits. If any issue is found, create a
follow-up task to fix it before merging.

---

## Verification Summary

Before considering the plan complete, verify:

- [ ] `python -m pytest tests/test_analyze_parallel.py -v` → all 18 tests pass
- [ ] `python -m pytest tests/ -v` → full suite passes (no regressions)
- [ ] `python main.py analyze --help` shows `--parallel` / `-j`
- [ ] `python main.py all --help` shows `--parallel` / `-j`
- [ ] Task 7 smoke tests completed manually with real repos
- [ ] All commits from Tasks 1-6 are on `feature/analyze-parallel` branch

## Out-of-Scope Reminders (YAGNI)

- Do NOT parallelize `parse_repo()` internals (routes/controllers/models/pages remain serial per repo)
- Do NOT parallelize screen analysis or usecase extraction
- Do NOT change the checkpoint file schema
- Do NOT add retry logic for failed repos (user re-runs with `--resume`)
- Do NOT introduce asyncio or multiprocessing
- Do NOT add per-worker logging infrastructure (use the main-thread `console.print` pattern from the spec)
