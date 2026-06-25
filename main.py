"""
RDRA Analyzer CLI エントリーポイント

Typer を使用したCLIインターフェース。
4つのパートを個別または一括で実行できる。
どんな言語・フレームワークのリポジトリにも対応（CLAUDE.md / AGENTS.md をコンテキストとして活用）。

使用例:
    # 全パートを実行
    python main.py all --repo /path/to/repo

    # パート1: ソースコード解析・UC抽出・画面分析
    python main.py analyze --repo /path/to/repo

    # パート2: RDRAモデル生成のみ
    python main.py rdra

    # パート3: CRUDギャップ分析のみ
    python main.py gap

    # パート4: E2Eテスト実行のみ
    python main.py e2e

    # 設定確認
    python main.py config
"""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from extraction.source_parser import RepoParseResult

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# .env ファイルの自動読み込み
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = typer.Typer(
    name="rdra",
    help="RDRA分析ツール - ユースケース抽出・RDRAモデル生成・CRUDギャップ分析・E2Eテスト（言語・フレームワーク非依存）",
    add_completion=False,
)
console = Console()

# 業務フロー協働 BC（③）— PdM 承認ループ（sync #5）
flow_app = typer.Typer(help="業務フロー承認ループ: 確定UCから想定→PdM承認→loop-e2e引き渡し")
app.add_typer(flow_app, name="flow")


def _get_config():
    """設定を取得して検証する"""
    from config import get_config
    config = get_config()
    return config


def _get_llm():
    """LLMプロバイダーを取得する"""
    from llm import get_provider
    return get_provider()


def _apply_repo_option(config, repo: Optional[list[str]]):
    """--repo CLIオプションで設定を上書きする"""
    if repo:
        config.repo_paths = [Path(r) for r in repo]


def _print_header(title: str) -> None:
    """セクションヘッダーを表示する"""
    console.print()
    console.print(Panel(f"[bold blue]{title}[/bold blue]", expand=False))


@app.command("config")
def show_config(
    repo: Optional[list[str]] = typer.Option(
        None, "--repo", "-r", help="解析対象リポジトリのパス（複数指定可）"
    ),
):
    """現在の設定値を表示する"""
    config = _get_config()
    _apply_repo_option(config, repo)

    table = Table(title="RDRA Analyzer 設定", show_header=True)
    table.add_column("設定項目", style="bold")
    table.add_column("値")

    table.add_row("LLMプロバイダー", "Claude Code CLI" if config.use_claude_code else "Anthropic API")
    table.add_row("使用モデル", config.claude_model)
    table.add_row("リポジトリパス", ", ".join(str(p) for p in config.repo_paths) or "(未設定)")
    table.add_row("出力ディレクトリ", str(config.output_dir))
    table.add_row("E2EベースURL", config.e2e_base_url)
    table.add_row("E2Eヘッドレス", str(config.e2e_headless))
    table.add_row("最大リトライ回数", str(config.e2e_max_retries))

    console.print(table)

    # パス存在確認
    console.print()
    for repo_path in config.repo_paths:
        exists = repo_path.exists()
        icon = "[green]OK[/green]" if exists else "[red]NG[/red]"
        console.print(f"  {icon} {repo_path}")

        # CLAUDE.md / AGENTS.md の存在チェック
        for ctx_file in ["CLAUDE.md", "AGENTS.md"]:
            ctx_path = repo_path / ctx_file
            if ctx_path.exists():
                console.print(f"      [dim]{ctx_file} あり[/dim]")

        # フレームワーク検出
        from context.project_context import build_context
        ctx = build_context(repo_path)
        if ctx.detected_frameworks:
            console.print(f"      [dim]フレームワーク: {', '.join(ctx.detected_frameworks)}[/dim]")


def _save_parse_checkpoint(data: dict, checkpoint_path: Path) -> None:
    """ソースコード解析の中間結果を保存する"""
    from extraction.source_parser import ParsedRoute, ParsedController, ParsedModel, ParsedPage

    def _route_to_dict(r: ParsedRoute) -> dict:
        return {"method": r.method, "path": r.path, "controller": r.controller,
                "action": r.action, "middleware": r.middleware, "prefix": r.prefix}

    def _controller_to_dict(c: ParsedController) -> dict:
        return {"class_name": c.class_name, "file_path": c.file_path,
                "namespace": c.namespace, "methods": c.methods,
                "docblocks": c.docblocks, "request_rules": c.request_rules}

    def _model_to_dict(m: ParsedModel) -> dict:
        return {"class_name": m.class_name, "table_name": m.table_name,
                "fillable": m.fillable, "relationships": m.relationships,
                "casts": m.casts, "scopes": m.scopes}

    def _page_to_dict(p: ParsedPage) -> dict:
        return {"route_path": p.route_path, "file_path": p.file_path,
                "component_name": p.component_name, "page_type": p.page_type,
                "api_calls": p.api_calls, "imported_hooks": p.imported_hooks,
                "form_fields": p.form_fields, "feature_component": p.feature_component}

    def _entity_operation_to_dict(op) -> dict:
        return {"entity_class": op.entity_class, "operation": op.operation,
                "method_signature": op.method_signature, "source_file": op.source_file,
                "source_class": op.source_class, "source_method": op.source_method,
                "call_chain": op.call_chain, "confidence": op.confidence}

    serializable = {
        "routes": [_route_to_dict(r) for r in data.get("routes", [])],
        "controllers": [_controller_to_dict(c) for c in data.get("controllers", [])],
        "models": [_model_to_dict(m) for m in data.get("models", [])],
        "pages": [_page_to_dict(p) for p in data.get("pages", [])],
        "entity_operations": [_entity_operation_to_dict(op) for op in data.get("entity_operations", [])],
        "completed_repos": data.get("completed_repos", []),
        "phase": data.get("phase", "parse"),
    }
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint_path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_parse_checkpoint(checkpoint_path: Path) -> dict | None:
    """ソースコード解析の中間結果を読み込む"""
    if not checkpoint_path.exists():
        return None
    from extraction.source_parser import ParsedRoute, ParsedController, ParsedModel, ParsedPage, EntityOperation

    data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    routes = [ParsedRoute(**r) for r in data.get("routes", [])]
    controllers = [ParsedController(**c) for c in data.get("controllers", [])]
    models = [ParsedModel(**m) for m in data.get("models", [])]
    pages = [ParsedPage(**p) for p in data.get("pages", [])]
    entity_operations = [EntityOperation(**op) for op in data.get("entity_operations", [])]
    return {
        "routes": routes,
        "controllers": controllers,
        "models": models,
        "pages": pages,
        "entity_operations": entity_operations,
        "completed_repos": data.get("completed_repos", []),
        "phase": data.get("phase", "parse"),
    }


_DEFAULT_AUTO_PARALLEL_CAP = 4  # LLM レート制限を考慮した保守的な上限


def _resolve_parallel(parallel: int, repo_count: int) -> int:
    """
    CLI `--parallel` 値を実行時の並列度に解決する。

    Args:
        parallel: CLI 引数値。0 は自動、1 以上はそのまま、負数はエラー。
        repo_count: 対象リポジトリ数。

    Returns:
        実際に ThreadPoolExecutor に渡す max_workers 値。
        parallel=0 の場合は min(_DEFAULT_AUTO_PARALLEL_CAP, repo_count)。
        repo_count が 0 の場合でも安全な値（1）を返す。

    Raises:
        typer.BadParameter: parallel が負の値のとき。
    """
    if parallel < 0:
        raise typer.BadParameter("--parallel must be >= 0")
    if parallel == 0:
        return min(_DEFAULT_AUTO_PARALLEL_CAP, repo_count) if repo_count > 0 else 1
    return parallel


def _parse_single_repo(repo_path: Path, parser) -> "RepoParseResult":
    """
    並列ワーカー: 1 リポジトリを解析し RepoParseResult を返す。

    例外は catch して success=False で包んで返すので、呼び出し側は
    Future.result() を例外ハンドリングなしで受け取れる。BaseException は
    意図的に捕捉しない（Ctrl-C で停止可能にするため）。

    ここでは build_context() を呼ばない。context は並列実行の外で
    config.repo_paths 順に事前構築する必要があるため。
    （parse_repo 内部では独自に build_context を呼ぶがそれは LLM プロンプト用）
    """
    from extraction.source_parser import RepoParseResult

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
            error=f"{type(e).__name__}: {e}",
        )


def _run_parallel_parse(
    pending_repos: list[Path],
    parser,
    parallel: int,
    on_complete: Optional[Callable[["RepoParseResult"], None]] = None,
) -> tuple[list["RepoParseResult"], list["RepoParseResult"]]:
    """
    pending_repos を ThreadPoolExecutor で並列に parse する。

    共有状態（all_routes, completed_repos, checkpoint ファイル等）の更新は
    呼び出し側の責務。このヘルパーは結果を (successes, failures) に分ける
    だけで、on_complete コールバック経由で呼び出し側にメインスレッドで
    1 件ずつ通知する（as_completed の順序 = 完了順）。

    Args:
        pending_repos: 解析対象のリポジトリパス一覧（completed_repos を除外済み）
        parser: SourceParser インスタンス（全ワーカーで共有される）。
                parse_repo(repo_path) はスレッドセーフである必要がある。
        parallel: max_workers（_resolve_parallel で解決済みの値）
        on_complete: 各 Future 完了時にメインスレッドで呼ばれる callback。
                     シグネチャ: (RepoParseResult) -> None

    Returns:
        (successes, failures) の 2 タプル。各要素は RepoParseResult のリスト。

    Note:
        on_complete が例外を送出した場合、例外はそのまま呼び出し側に伝播する。
        ThreadPoolExecutor の context manager は残りの future 完了を待ってから
        抜けるため、実行中のワーカーはキャンセルされずに完走する（結果は破棄）。
        checkpoint はその例外より前の on_complete 呼び出しで書き込まれた状態が
        残る。
    """
    successes: list["RepoParseResult"] = []
    failures: list["RepoParseResult"] = []

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


@app.command("analyze")
def run_analyze(
    repo: Optional[list[str]] = typer.Option(
        None, "--repo", "-r", help="解析対象リポジトリのパス（複数指定可）"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ（省略時は ./output）"
    ),
    max_routes: int = typer.Option(
        200, "--max-routes", help="解析する最大ルート数"
    ),
    skip_llm: bool = typer.Option(
        False, "--skip-llm", help="LLM呼び出しをスキップ（最低限の解析のみ）"
    ),
    resume: bool = typer.Option(
        False, "--resume", help="前回の中断箇所から再開する"
    ),
    checkpoint_interval: int = typer.Option(
        30, "--checkpoint-interval", help="中間保存の間隔（ルート件数単位）"
    ),
    batch_size: int = typer.Option(
        5, "--batch-size", "-b", help="画面分析の1バッチあたりのページ数"
    ),
    parallel: int = typer.Option(
        0, "--parallel", "-j",
        help="リポジトリ並列度（0=自動: min(4, リポ数)、1=直列）"
    ),
    strict: bool = typer.Option(
        False, "--strict",
        help="Precision重視: コード証拠に紐づかないUCを確定モデルから棄却し棄却ログへ退避（sync #1）"
    ),
):
    """
    パート1: ソースコード解析 → ユースケース抽出 → 画面分析

    対象リポジトリの CLAUDE.md / AGENTS.md をコンテキストとして活用し、
    言語・フレームワークに依存しない動的な解析を行う。

    --resume で前回タイムアウト等の中断から再開可能。
    中間結果は output/usecases/_checkpoint.json に保存される。
    """
    _print_header("パート1: ソースコード解析・画面分析・ユースケース抽出")

    config = _get_config()
    _apply_repo_option(config, repo)
    output_dir = output_dir or config.output_dir
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        config.validate()
    except ValueError as e:
        console.print(f"[red]設定エラー: {e}[/red]")
        raise typer.Exit(1)

    # LLM プロバイダーを取得
    llm = None
    if not skip_llm:
        llm = _get_llm()

    checkpoint_path = output_dir / "usecases" / "_checkpoint.json"
    output_path = output_dir / "usecases" / "analysis_result.json"

    # チェックポイントからの再開
    checkpoint = None
    if resume:
        checkpoint = _load_parse_checkpoint(checkpoint_path)
        if checkpoint:
            console.print(f"[cyan]チェックポイントから再開します[/cyan]")
            console.print(
                f"  既存データ: ルート {len(checkpoint['routes'])}件 | "
                f"モデル {len(checkpoint['models'])}件 | "
                f"完了リポ {checkpoint['completed_repos']}"
            )
        else:
            console.print("[yellow]チェックポイントが見つかりません。最初から実行します。[/yellow]")

    # ソースコード解析（全リポジトリ統合）
    all_routes = checkpoint["routes"] if checkpoint else []
    all_controllers = checkpoint["controllers"] if checkpoint else []
    all_models = checkpoint["models"] if checkpoint else []
    all_pages = checkpoint["pages"] if checkpoint else []
    all_entity_operations = checkpoint.get("entity_operations", []) if checkpoint else []
    all_contexts = []
    completed_repos = set(checkpoint["completed_repos"]) if checkpoint else set()

    from extraction.source_parser import SourceParser
    from context.project_context import format_context_for_prompt, build_context
    parser = SourceParser(llm_provider=llm)

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

    effective_parallel = _resolve_parallel(parallel, len(pending_repos))
    failed_repos: list[tuple[str, str]] = []

    if pending_repos:
        console.print(
            f"\n  [並列度 {effective_parallel}] "
            f"{len(pending_repos)} リポジトリを解析中..."
        )

        # 並列完了順ではなく repo_paths 順でマージするため、
        # 結果をリポ名→RepoParseResult の辞書に保持する。
        # checkpoint は完了ごとに incremental 保存する。
        pending_results: dict[str, "RepoParseResult"] = {}

        def _on_repo_complete(result):
            if result.success:
                pending_results[result.repo_name] = result
                completed_repos.add(result.repo_name)
                console.print(
                    f"  [green]OK[/green] {result.repo_name}: "
                    f"ルート {len(result.routes)} / "
                    f"モデル {len(result.models)} / "
                    f"ページ {len(result.pages)} / "
                    f"エンティティ操作 {len(result.entity_operations)}"
                )
                # incremental checkpoint: 完了順で一旦集約
                _inc_routes = all_routes + [
                    r for res in pending_results.values() for r in res.routes
                ]
                _inc_controllers = all_controllers + [
                    c for res in pending_results.values() for c in res.controllers
                ]
                _inc_models = all_models + [
                    m for res in pending_results.values() for m in res.models
                ]
                _inc_pages = all_pages + [
                    p for res in pending_results.values() for p in res.pages
                ]
                _inc_entity_ops = all_entity_operations + [
                    op for res in pending_results.values() for op in res.entity_operations
                ]
                _save_parse_checkpoint({
                    "routes": _inc_routes, "controllers": _inc_controllers,
                    "models": _inc_models, "pages": _inc_pages,
                    "entity_operations": _inc_entity_ops,
                    "completed_repos": list(completed_repos), "phase": "parse",
                }, checkpoint_path)
            else:
                failed_repos.append((result.repo_name, result.error))
                console.print(
                    f"  [red]NG {result.repo_name}: 失敗 - {result.error}[/red]"
                )

        _run_parallel_parse(
            pending_repos=pending_repos,
            parser=parser,
            parallel=effective_parallel,
            on_complete=_on_repo_complete,
        )

        # repo_paths の順序でマージ（max_routes truncation が決定的になる）
        for rp in config.repo_paths:
            result = pending_results.get(rp.name)
            if result:
                all_routes.extend(result.routes)
                all_controllers.extend(result.controllers)
                all_models.extend(result.models)
                all_pages.extend(result.pages)
                all_entity_operations.extend(result.entity_operations)

    if failed_repos:
        console.print(
            f"\n  [green]成功: {len(completed_repos)}/{len(config.repo_paths)}[/green] | "
            f"[red]失敗: {len(failed_repos)}[/red]"
        )
        for name, err in failed_repos:
            console.print(f"  [red]失敗リポ: {name} - {err}[/red]")
        console.print(
            "  [yellow]--resume で再実行すると失敗したリポだけ再試行されます[/yellow]"
        )
        if len(failed_repos) == len(config.repo_paths):
            raise typer.Exit(1)

    routes = all_routes[:max_routes]

    # チェックポイントを更新（ソースコード解析完了）
    _save_parse_checkpoint({
        "routes": all_routes, "controllers": all_controllers,
        "models": all_models, "pages": all_pages,
        "entity_operations": all_entity_operations,
        "completed_repos": list(completed_repos), "phase": "parsed",
    }, checkpoint_path)

    # 画面分析（UC抽出の前に実行し、結果をUC抽出に活用）
    screen_specs = []
    screen_path = output_dir / "usecases" / "screen_specs.json"

    # 既存の画面仕様があれば読み込んでスキップ
    if resume and screen_path.exists():
        from extraction.screen_analyzer import ScreenAnalyzer
        screen_specs = ScreenAnalyzer.load_from_json(screen_path)
        if screen_specs:
            console.print(f"\n  [cyan]既存の画面仕様 {len(screen_specs)}件を読み込み（スキップ）[/cyan]")

    if not screen_specs and all_pages and not skip_llm:
        console.print()
        _print_header("画面分析")
        from extraction.source_parser import ParsedPage
        from extraction.screen_analyzer import ScreenAnalyzer

        screen_analyzer = ScreenAnalyzer(llm)

        # フロントエンドリポジトリを特定
        frontend_repo = None
        for rp in config.repo_paths:
            if "frontend" in str(rp).lower() or "admin" in str(rp).lower():
                frontend_repo = rp
                break
        if not frontend_repo and config.repo_paths:
            frontend_repo = config.repo_paths[-1]

        if frontend_repo:
            console.print(f"  対象リポジトリ: {frontend_repo.name}")
            console.print(f"  ページ数: {len(all_pages)}件")

            total_batches = (len(all_pages) + batch_size - 1) // batch_size
            console.print(f"  バッチ数: {total_batches}（{batch_size}ページ/バッチ）")

            # Phase A: レイアウト
            console.print("[dim]共有レイアウトを抽出中...[/dim]")
            shared_layouts = screen_analyzer._extract_shared_layouts(
                frontend_repo, screen_analyzer._project_context
            )
            console.print(f"  -> レイアウト: {len(shared_layouts)}件")

            # Phase B: 個別ページをバッチで
            ctx = build_context(frontend_repo)
            context_text = format_context_for_prompt([ctx])

            parsed_pages = [
                p if isinstance(p, ParsedPage) else ParsedPage(**p)
                for p in all_pages
            ]
            batches = [parsed_pages[i:i+batch_size] for i in range(0, len(parsed_pages), batch_size)]
            for batch_idx, batch in enumerate(batches):
                console.print(f"  バッチ {batch_idx+1}/{len(batches)} ({len(batch)}ページ)...")
                batch_specs = screen_analyzer._extract_screen_batch(
                    frontend_repo, batch, context_text, shared_layouts,
                    batch_idx, len(batches)
                )
                screen_specs.extend(batch_specs)
                console.print(f"    -> {len(batch_specs)}画面抽出")

                # 中間保存
                screen_path = output_dir / "usecases" / "screen_specs.json"
                ScreenAnalyzer.save_to_json(screen_specs, screen_path)

            # ナビゲーショングラフ構築
            screen_analyzer._build_navigation_graph(screen_specs)
            for spec in screen_specs:
                if spec.shared_layout and spec.shared_layout in shared_layouts:
                    spec.shared_nav_items = shared_layouts[spec.shared_layout]

            # 最終保存
            screen_path = output_dir / "usecases" / "screen_specs.json"
            ScreenAnalyzer.save_to_json(screen_specs, screen_path)

            console.print(f"  -> 画面分析完了: {len(screen_specs)}件")
            console.print(f"  出力: {screen_path}")
        else:
            console.print("[yellow]フロントエンドリポジトリが特定できません。[/yellow]")
    elif not all_pages:
        console.print("\n[yellow]ページが検出されなかったため画面分析をスキップします。[/yellow]")

    # ユースケース抽出（画面分析結果を活用）
    if skip_llm:
        console.print("[yellow]LLM呼び出しをスキップします[/yellow]")
        from extraction.usecase_extractor import UseCaseExtractor
        extractor = UseCaseExtractor(None)
        usecases = extractor._fallback_extraction(routes)
        usecases = extractor._assign_ids(extractor._deduplicate(usecases))
    else:
        console.print()
        _print_header("ユースケース抽出")

        # 既存のユースケースがあれば再開
        existing_usecases = []
        if resume and output_path.exists():
            try:
                data = json.loads(output_path.read_text(encoding="utf-8"))
                existing_usecases, _ = _load_analysis_result(data)
                if existing_usecases:
                    console.print(f"  [cyan]既存ユースケース {len(existing_usecases)}件を読み込み[/cyan]")
            except Exception:
                pass

        # プロジェクトコンテキストを構築
        project_context_text = format_context_for_prompt(all_contexts)

        if existing_usecases and resume:
            usecases = existing_usecases
            console.print(f"  -> ユースケース: {len(usecases)}件（再開）")
        else:
            # LLMでユースケース抽出（画面仕様をコンテキストに含める）
            console.print("[dim]LLMでユースケースを抽出中...[/dim]")
            if screen_specs:
                console.print(f"  [dim]画面仕様 {len(screen_specs)}件をコンテキストに含めます[/dim]")
            from extraction.usecase_extractor import UseCaseExtractor
            extractor = UseCaseExtractor(llm, project_context=project_context_text)

            # バッチ処理を手動で行い、中間ログ出力
            context = extractor._build_context(
                all_controllers, all_models, all_pages,
                screen_specs=screen_specs,
            )
            route_batches = extractor._split_into_batches(routes, checkpoint_interval)
            usecases = []

            for batch_idx, batch in enumerate(route_batches):
                console.print(
                    f"  バッチ {batch_idx + 1}/{len(route_batches)} "
                    f"（ルート {len(batch)}件）..."
                )
                batch_usecases = extractor._extract_batch(
                    batch, context, batch_idx, len(route_batches)
                )
                usecases.extend(batch_usecases)
                console.print(f"    -> 抽出: {len(batch_usecases)}件（累計: {len(usecases)}件）")

                # 中間保存
                temp_usecases = extractor._assign_ids(extractor._deduplicate(list(usecases)))
                from shared.scenario_builder import ScenarioBuilder
                builder = ScenarioBuilder(llm)
                builder.save_to_json(temp_usecases, [], output_path)
                console.print(f"    [dim]-> 中間保存: {output_path}[/dim]")

            usecases = extractor._deduplicate(usecases)
            usecases = extractor._assign_ids(usecases)
            console.print(f"  -> ユースケース: {len(usecases)}件（重複除去後）")

        # Precision 棄却（opt-in）: コード証拠なき UC を確定モデルから外し棄却ログへ（sync #1）
        if strict:
            from extraction.rejection_log import partition_usecases, rejected_to_dict
            usecases, rejected = partition_usecases(usecases)
            rejection_path = output_dir / "usecases" / "rejection_log.json"
            rejection_path.parent.mkdir(parents=True, exist_ok=True)
            rejection_path.write_text(
                json.dumps(
                    {"rejected": [rejected_to_dict(r) for r in rejected]},
                    ensure_ascii=False, indent=2,
                ),
                encoding="utf-8",
            )
            console.print(
                f"  [yellow]Precision棄却: 確定 {len(usecases)}件 / 棄却 {len(rejected)}件"
                f"[/yellow] -> {rejection_path}"
            )

        # ユースケースを保存
        from shared.scenario_builder import ScenarioBuilder
        builder = ScenarioBuilder(llm)
        builder.save_to_json(usecases, [], output_path)
        console.print(f"  [dim]-> ユースケースを保存: {output_path}[/dim]")

    # チェックポイントを更新（フェーズ完了）
    _save_parse_checkpoint({
        "routes": all_routes, "controllers": all_controllers,
        "models": all_models, "pages": all_pages,
        "entity_operations": all_entity_operations,
        "completed_repos": list(completed_repos), "phase": "done",
    }, checkpoint_path)

    console.print(f"\n[green]解析完了[/green]")
    console.print(f"  出力ファイル: {output_path}")

    return usecases, screen_specs, routes, all_models


@app.command("reconcile")
def run_reconcile(
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ"
    ),
    pending_file: Optional[Path] = typer.Option(
        None, "--pending", help="loop-e2e-pending.json のパス（省略時は output/usecases/）"
    ),
):
    """
    loop-e2e 連携: loop-e2e-pending.json を取り込む（reconcile）

    loop-e2e の 'rdra-export' がルート照合で当てられなかったシナリオを、
    checkpoint でソースに当てて事実確認し、既存UC紐付け or 新規UC生成で
    analysis_result.json に取り込む。LE- シナリオは loop-e2e 所有として冪等に扱う。
    """
    _print_header("loop-e2e シナリオ取り込み (reconcile)")
    from reconciliation.reconcile import reconcile, apply_reconcile, validate

    config = _get_config()
    output_dir = Path(output_dir or config.output_dir)
    uc_dir = output_dir / "usecases"
    analysis_path = uc_dir / "analysis_result.json"
    pending_path = pending_file or (uc_dir / "loop-e2e-pending.json")
    checkpoint_path = uc_dir / "_checkpoint.json"

    if not analysis_path.exists():
        console.print(
            "[red]analysis_result.json が見つかりません。先に 'analyze' を実行してください。[/red]"
        )
        raise typer.Exit(1)
    if not pending_path.exists():
        console.print(
            f"[yellow]{pending_path} が見つかりません。取り込むものがありません。[/yellow]"
        )
        raise typer.Exit(0)

    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    checkpoint = (
        json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if checkpoint_path.exists()
        else {}
    )

    entries = pending.get("pending", [])
    console.print(
        f"  pending: {len(entries)}件 | 既存UC: {len(analysis.get('usecases', []))}件"
    )
    if not checkpoint:
        console.print(
            "[yellow]checkpoint が無いため事実確認できません（ルート照合のみ）。[/yellow]"
        )
    if not entries:
        console.print("[green]取り込む pending はありません。[/green]")
        raise typer.Exit(0)

    # 棄却ログを読み、救済（静的棄却UC＋loop-e2e実績→再昇格）の候補にする。sync #1 follow-on
    from extraction.rejection_log import load_rejected, rejected_to_dict
    rejection_path = uc_dir / "rejection_log.json"
    rejected = (
        load_rejected(json.loads(rejection_path.read_text(encoding="utf-8")))
        if rejection_path.exists()
        else []
    )

    result = reconcile(analysis, pending, checkpoint, rejected=rejected)
    merged = apply_reconcile(analysis, result)

    # 参照整合性チェック: 失敗時は書き戻さない
    try:
        validate(merged)
    except ValueError as e:
        console.print(f"[red]参照整合性チェック失敗: {e}[/red]")
        console.print("[red]analysis_result.json は変更していません。[/red]")
        raise typer.Exit(1)

    analysis_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # 取り込み済み pending を空にして書き戻す
    pending["pending"] = []
    pending_path.write_text(
        json.dumps(pending, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 救済された UC を棄却ログから除去して書き戻す（もう棄却ではない）。sync #1 follow-on
    if result.rescued and rejection_path.exists():
        rescued_ids = {uc.id for uc in result.rescued}
        remaining = [r for r in rejected if r.id not in rescued_ids]
        rejection_path.write_text(
            json.dumps(
                {"rejected": [rejected_to_dict(r) for r in remaining]},
                ensure_ascii=False, indent=2,
            ),
            encoding="utf-8",
        )

    # 矛盾（要調査）レポートを出力（コードを真・UC は上書きしない）。sync #4
    from reconciliation.conflict_report import conflict_to_dict
    conflict_path = uc_dir / "conflict_report.json"
    conflict_path.write_text(
        json.dumps(
            {"conflicts": [conflict_to_dict(c) for c in result.conflicts]},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )

    console.print(f"\n[green]取り込み完了[/green]")
    console.print(f"  既存UCに紐付け: {result.linked}件")
    console.print(f"  新規UC生成: {result.created}件")
    if result.rescued:
        console.print(
            f"  [cyan]棄却UCを実績で救済: {len(result.rescued)}件（実績由来・derived）[/cyan]"
        )
    console.print(f"  取り込みシナリオ: {len(result.reconciled)}件 (LE-)")
    if result.conflicts:
        console.print(
            f"  [yellow]要調査の矛盾: {len(result.conflicts)}件（コードを真）[/yellow] -> {conflict_path}"
        )
    console.print(f"  -> {analysis_path}")


@app.command("enrich")
def run_enrich(
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ"
    ),
):
    """
    ユースケースの related_* を checkpoint から再導出する（LLM不要）

    既存 analysis_result.json の related_controllers / related_views /
    related_pages を _checkpoint.json（routes / pages）から決定的に埋め直して保存する。
    古い生成物の補完や、reconcile で新規UCを足した後のリフレッシュに使う。
    related_pages は loop-e2e の navigate 照合・reconcile の紐付けキーになる。
    """
    _print_header("ユースケース related_* 補完 (enrich)")
    from extraction.source_parser import ParsedRoute, ParsedPage
    from extraction.usecase_extractor import UseCaseExtractor
    from reconciliation.reconcile import _usecase_to_dict
    from extraction.source_parser import from_checkpoint_dict

    config = _get_config()
    output_dir = Path(output_dir or config.output_dir)
    uc_dir = output_dir / "usecases"
    analysis_path = uc_dir / "analysis_result.json"
    cp_path = uc_dir / "_checkpoint.json"

    if not analysis_path.exists() or not cp_path.exists():
        console.print(
            "[red]analysis_result.json または _checkpoint.json が見つかりません。"
            "先に 'analyze' を実行してください。[/red]"
        )
        raise typer.Exit(1)

    try:
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
        usecases, _ = _load_analysis_result(data)
        cp = json.loads(cp_path.read_text(encoding="utf-8"))
        routes = [from_checkpoint_dict(ParsedRoute, r) for r in cp.get("routes", [])]
        pages = [from_checkpoint_dict(ParsedPage, p) for p in cp.get("pages", [])]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        console.print(
            f"[red]入力ファイルの読み込みに失敗しました: {e}[/red]\n"
            "  analysis_result.json / _checkpoint.json が壊れている可能性があります。"
        )
        raise typer.Exit(1)
    console.print(
        f"  UC: {len(usecases)}件 | routes: {len(routes)}件 | pages: {len(pages)}件"
    )

    extractor = UseCaseExtractor(None)
    extractor._enrich_controllers(usecases, routes)
    extractor._enrich_pages(usecases, pages)

    # usecases のみ更新。scenarios・未知トップレベルフィールドは温存する
    data["usecases"] = [_usecase_to_dict(u) for u in usecases]
    md = dict(data.get("metadata", {}))
    md["total_usecases"] = len(usecases)
    md["total_scenarios"] = len(data.get("scenarios", []))
    data["metadata"] = md
    analysis_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    c = sum(1 for u in usecases if u.related_controllers)
    v = sum(1 for u in usecases if u.related_views)
    p = sum(1 for u in usecases if u.related_pages)
    console.print("\n[green]補完完了[/green]")
    console.print(f"  related_controllers 非空: {c}/{len(usecases)}")
    console.print(f"  related_views 非空: {v}/{len(usecases)}")
    console.print(f"  related_pages 非空: {p}/{len(usecases)}")
    console.print(f"  -> {analysis_path}")


@app.command("screens")
def run_screens(
    repo: Optional[list[str]] = typer.Option(
        None, "--repo", "-r", help="フロントエンドリポジトリのパス"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ"
    ),
    batch_size: int = typer.Option(
        5, "--batch-size", "-b", help="1バッチあたりのページ数"
    ),
):
    """
    画面分析: フロントエンドのUI要素を詳細に抽出する。

    ボタン・フォーム・モーダル・タブ・ナビゲーション等を
    実際のコンポーネントから抽出し screen_specs.json に保存する。
    """
    _print_header("画面分析")

    config = _get_config()
    _apply_repo_option(config, repo)
    output_dir = output_dir or config.output_dir
    output_dir = Path(output_dir)

    # ページ一覧を読み込む
    cp_path = output_dir / "usecases" / "_checkpoint.json"
    if not cp_path.exists():
        console.print("[red]チェックポイントが見つかりません。先に 'analyze' を実行してください。[/red]")
        raise typer.Exit(1)

    from extraction.source_parser import ParsedPage
    cp = json.loads(cp_path.read_text(encoding="utf-8"))
    pages = [ParsedPage(**p) for p in cp.get("pages", [])]
    console.print(f"  ページ数: {len(pages)}件")

    if not pages:
        console.print("[yellow]解析済みページがありません。[/yellow]")
        raise typer.Exit(0)

    llm = _get_llm()
    from extraction.screen_analyzer import ScreenAnalyzer
    analyzer = ScreenAnalyzer(llm)

    # フロントエンドリポジトリを特定
    frontend_repo = None
    for rp in config.repo_paths:
        if "frontend" in str(rp).lower() or "admin" in str(rp).lower():
            frontend_repo = rp
            break
    if not frontend_repo and config.repo_paths:
        frontend_repo = config.repo_paths[-1]  # 最後のリポジトリをフロントエンドと仮定

    if not frontend_repo:
        console.print("[red]フロントエンドリポジトリが特定できません。--repo で指定してください。[/red]")
        raise typer.Exit(1)

    console.print(f"  対象リポジトリ: {frontend_repo.name}")

    total_batches = (len(pages) + batch_size - 1) // batch_size
    console.print(f"  バッチ数: {total_batches}（{batch_size}ページ/バッチ）")

    specs = []
    # Phase A: レイアウト
    console.print("[dim]共有レイアウトを抽出中...[/dim]")
    shared_layouts = analyzer._extract_shared_layouts(frontend_repo, analyzer._project_context)
    console.print(f"  -> レイアウト: {len(shared_layouts)}件")

    # Phase B: 個別ページをバッチで
    from context.project_context import build_context, format_context_for_prompt
    ctx = build_context(frontend_repo)
    context_text = format_context_for_prompt([ctx])

    batches = [pages[i:i+batch_size] for i in range(0, len(pages), batch_size)]
    for batch_idx, batch in enumerate(batches):
        console.print(f"  バッチ {batch_idx+1}/{len(batches)} ({len(batch)}ページ)...")
        batch_specs = analyzer._extract_screen_batch(
            frontend_repo, batch, context_text, shared_layouts, batch_idx, len(batches)
        )
        specs.extend(batch_specs)
        console.print(f"    -> {len(batch_specs)}画面抽出")

        # 中間保存
        screen_path = output_dir / "usecases" / "screen_specs.json"
        ScreenAnalyzer.save_to_json(specs, screen_path)

    # ナビゲーショングラフ構築
    analyzer._build_navigation_graph(specs)
    for spec in specs:
        if spec.shared_layout and spec.shared_layout in shared_layouts:
            spec.shared_nav_items = shared_layouts[spec.shared_layout]

    # 最終保存
    screen_path = output_dir / "usecases" / "screen_specs.json"
    ScreenAnalyzer.save_to_json(specs, screen_path)

    console.print(f"\n[green]画面分析完了[/green]")
    console.print(f"  画面数: {len(specs)}件")
    console.print(f"  出力: {screen_path}")


@app.command("rdra")
def run_rdra(
    repo: Optional[list[str]] = typer.Option(
        None, "--repo", "-r", help="解析対象リポジトリのパス（複数指定可）"
    ),
    input_file: Optional[Path] = typer.Option(
        None, "--input", "-i",
        help="パート1の出力JSONファイル（省略時は自動解析）"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ"
    ),
):
    """
    パート2: RDRAモデル生成

    情報モデル・ユースケース複合図・アクティビティ図を
    Mermaid記法のMarkdownファイルとして出力する。
    """
    _print_header("パート2: RDRAモデル生成")

    config = _get_config()
    _apply_repo_option(config, repo)
    output_dir = output_dir or config.output_dir
    output_dir = Path(output_dir)

    # 入力データの読み込み（analyze の出力を再利用）
    if input_file and input_file.exists():
        console.print(f"[dim]入力ファイルを読み込み中: {input_file}[/dim]")
        data = json.loads(input_file.read_text(encoding="utf-8"))
        usecases, scenarios = _load_analysis_result(data)
    else:
        default_input = output_dir / "usecases" / "analysis_result.json"
        if default_input.exists():
            data = json.loads(default_input.read_text(encoding="utf-8"))
            usecases, scenarios = _load_analysis_result(data)
        else:
            console.print("[red]解析結果が見つかりません: analysis_result.json[/red]")
            console.print("先に 'python main.py analyze' を実行してください。")
            raise typer.Exit(1)

    # チェックポイントからモデル・ルート・コントローラーを読み込む
    checkpoint_path = output_dir / "usecases" / "_checkpoint.json"
    if not checkpoint_path.exists():
        console.print("[red]チェックポイントが見つかりません: _checkpoint.json[/red]")
        console.print("先に 'python main.py analyze' を実行してください。")
        raise typer.Exit(1)

    cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    missing = []
    if not cp.get("models"):
        missing.append("モデル（models）")
    if not cp.get("routes"):
        missing.append("ルート（routes）")
    if not cp.get("controllers"):
        missing.append("コントローラー（controllers）")
    if missing:
        console.print(f"[red]チェックポイントに以下のデータが不足しています: {', '.join(missing)}[/red]")
        console.print("'python main.py analyze' を再実行してください。")
        raise typer.Exit(1)

    from extraction.source_parser import ParsedRoute, ParsedController, ParsedModel, EntityOperation
    models = [ParsedModel(**m) if isinstance(m, dict) else m for m in cp["models"]]
    all_routes = [ParsedRoute(**r) if isinstance(r, dict) else r for r in cp["routes"]]
    all_controllers = [ParsedController(**c) if isinstance(c, dict) else c for c in cp["controllers"]]
    all_entity_ops = [
        EntityOperation(**eo) if isinstance(eo, dict) else eo
        for eo in (cp.get("entity_operations") or [])
    ]
    console.print(f"  チェックポイントから読み込み: ルート {len(all_routes)}件 | コントローラー {len(all_controllers)}件 | モデル {len(models)}件 | エンティティ操作 {len(all_entity_ops)}件")

    # プロジェクトコンテキスト構築
    project_context_text = ""
    if config.repo_paths:
        from context.project_context import build_context, format_context_for_prompt
        all_contexts = [build_context(rp) for rp in config.repo_paths]
        project_context_text = format_context_for_prompt(all_contexts)

    llm = _get_llm()

    # 情報モデル生成
    console.print("[dim]情報モデルを生成中...[/dim]")
    from extraction.derived.information_model import InformationModelGenerator
    info_gen = InformationModelGenerator(llm, project_context=project_context_text)
    entities, relationships = info_gen.generate(models)
    console.print(f"  -> エンティティ: {len(entities)}件 | リレーション: {len(relationships)}件")

    # ユースケース複合図・アクティビティ図・状態遷移図・ビジネスポリシーの生成と保存
    from visualization.usecase_diagram import UseCaseDiagramGenerator
    from visualization.activity_diagram import ActivityDiagramGenerator
    from extraction.derived.state_transition import StateTransitionGenerator
    from extraction.derived.business_policy import BusinessPolicyExtractor
    from visualization.mermaid_renderer import MermaidRenderer

    state_gen = StateTransitionGenerator(llm, project_context=project_context_text)
    bp_ext = BusinessPolicyExtractor(llm, project_context=project_context_text)

    # プロジェクト名をリポジトリ名から取得
    project_name = ", ".join(rp.name for rp in config.repo_paths) if config.repo_paths else ""

    renderer = MermaidRenderer(
        info_model_gen=info_gen,
        usecase_diagram_gen=UseCaseDiagramGenerator(llm),
        activity_diagram_gen=ActivityDiagramGenerator(),
        state_transition_gen=state_gen,
        business_policy_ext=bp_ext,
        project_name=project_name,
    )

    console.print("[dim]Mermaidダイアグラムを生成・保存中...[/dim]")
    saved_files = renderer.render_all(
        entities=entities,
        relationships=relationships,
        usecases=usecases,
        scenarios=scenarios,
        output_dir=output_dir,
        routes=all_routes,
        controllers=all_controllers,
        entity_operations=all_entity_ops,
    )

    # システム境界図（接点＝画面 × 起点＝エンドポイント）を決定的に生成。sync #3
    from extraction.derived.system_boundary import SystemBoundaryGenerator
    boundary_mermaid = SystemBoundaryGenerator().generate_mermaid(usecases)
    boundary_path = output_dir / "rdra" / "system_boundary.md"
    boundary_path.parent.mkdir(parents=True, exist_ok=True)
    boundary_path.write_text(
        "# システム境界図\n\n"
        "> 接点（画面）× 起点（API エンドポイント）の対応。enrich 照合から決定的に生成"
        "（派生層・確度=derived、新規生成ではなく既存照合の意味づけ）。\n\n"
        f"```mermaid\n{boundary_mermaid}\n```\n",
        encoding="utf-8",
    )

    console.print(f"\n[green]RDRAモデル生成完了[/green]")
    console.print(f"  生成ファイル数: {len(saved_files)}")
    console.print(f"  システム境界図: {boundary_path}")
    console.print(f"  インデックス: {output_dir}/rdra/index.md")


@app.command("gap")
def run_gap(
    repo: Optional[list[str]] = typer.Option(
        None, "--repo", "-r", help="解析対象リポジトリのパス（複数指定可）"
    ),
    input_file: Optional[Path] = typer.Option(
        None, "--input", "-i", help="パート1の出力JSONファイル"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ"
    ),
):
    """
    パート3: CRUDギャップ分析

    情報モデルの各エンティティに対して
    Create/Read/Update/Delete が存在するか確認し、
    不足操作をMarkdownテーブルで出力する。
    """
    _print_header("パート3: CRUDギャップ分析")

    config = _get_config()
    _apply_repo_option(config, repo)
    output_dir = output_dir or config.output_dir
    output_dir = Path(output_dir)

    # 入力データ読み込み
    input_file = input_file or (output_dir / "usecases" / "analysis_result.json")
    if not input_file.exists():
        console.print("[red]解析結果が見つかりません: analysis_result.json[/red]")
        console.print("先に 'python main.py analyze' を実行してください。")
        raise typer.Exit(1)

    data = json.loads(input_file.read_text(encoding="utf-8"))
    usecases, scenarios = _load_analysis_result(data)

    # チェックポイントからルート・モデルを読み込む
    checkpoint_path = output_dir / "usecases" / "_checkpoint.json"
    if not checkpoint_path.exists():
        console.print("[red]チェックポイントが見つかりません: _checkpoint.json[/red]")
        console.print("先に 'python main.py analyze' を実行してください。")
        raise typer.Exit(1)

    cp = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    missing = []
    if not cp.get("models"):
        missing.append("モデル（models）")
    if not cp.get("routes"):
        missing.append("ルート（routes）")
    if missing:
        console.print(f"[red]チェックポイントに以下のデータが不足しています: {', '.join(missing)}[/red]")
        console.print("'python main.py analyze' を再実行してください。")
        raise typer.Exit(1)

    from extraction.source_parser import ParsedRoute, ParsedModel, EntityOperation
    routes = [ParsedRoute(**r) if isinstance(r, dict) else r for r in cp["routes"]]
    models = [ParsedModel(**m) if isinstance(m, dict) else m for m in cp["models"]]
    entity_operations = [
        EntityOperation(**op) if isinstance(op, dict) else op
        for op in cp.get("entity_operations", [])
    ]
    console.print(f"  チェックポイントから読み込み: ルート {len(routes)}件 | モデル {len(models)}件 | エンティティ操作 {len(entity_operations)}件")

    # プロジェクトコンテキスト構築
    project_context_text = ""
    if config.repo_paths:
        from context.project_context import build_context, format_context_for_prompt
        all_contexts = [build_context(rp) for rp in config.repo_paths]
        project_context_text = format_context_for_prompt(all_contexts)

    # エンティティ生成（LLMなしで実行）
    from extraction.derived.information_model import InformationModelGenerator
    info_gen = InformationModelGenerator(None, project_context=project_context_text)
    entities, _ = info_gen.generate(models)

    # CRUDギャップ分析
    console.print("[dim]CRUDギャップを分析中...[/dim]")
    from extraction.derived.crud_analyzer import CrudAnalyzer
    analyzer = CrudAnalyzer()
    statuses, gaps = analyzer.analyze(entities, routes, scenarios, usecases, entity_operations)

    covered = sum(1 for s in statuses if s.coverage_percentage == 100)
    console.print(f"  -> エンティティ: {len(statuses)}件")
    console.print(f"  -> CRUD完全網羅: {covered}件")
    console.print(f"  -> ギャップ数: {len(gaps)}件")

    output_path = output_dir / "gap" / "crud_gap_analysis.md"
    analyzer.save_to_markdown(statuses, gaps, output_path)

    console.print(f"\n[green]CRUDギャップ分析完了[/green]")
    console.print(f"  出力ファイル: {output_path}")


def _build_viewer(output_dir: Path) -> str:
    """既存の解析結果・RDRAモデルからビューワーHTMLを再生成する"""
    import re
    from extraction.derived.information_model import InformationModelGenerator
    from visualization.mermaid_renderer import MermaidRenderer
    from visualization.usecase_diagram import UseCaseDiagramGenerator
    from visualization.activity_diagram import ActivityDiagramGenerator
    from extraction.derived.state_transition import StateTransitionGenerator, EntityStateMachine, StateTransition
    from extraction.derived.business_policy import BusinessPolicy
    from extraction.usecase_extractor import UseCaseExtractor
    from extraction.source_parser import ParsedModel, ParsedRoute

    # ---- ユースケース・シナリオ読み込み ----
    analysis_path = output_dir / "usecases" / "analysis_result.json"
    if not analysis_path.exists():
        raise FileNotFoundError(f"解析結果が見つかりません: {analysis_path}")
    data = json.loads(analysis_path.read_text(encoding="utf-8"))
    usecases, scenarios = _load_analysis_result(data)

    # ---- チェックポイントからモデル・ルート読み込み ----
    cp_path = output_dir / "usecases" / "_checkpoint.json"
    models, routes, pages = [], [], []
    if cp_path.exists():
        cp = json.loads(cp_path.read_text(encoding="utf-8"))
        from extraction.source_parser import ParsedPage, from_checkpoint_dict
        models = [from_checkpoint_dict(ParsedModel, m) for m in cp.get("models", [])]
        routes = [from_checkpoint_dict(ParsedRoute, r) for r in cp.get("routes", [])]
        pages = [from_checkpoint_dict(ParsedPage, p) for p in cp.get("pages", [])]

    # コントローラー・ページ紐付け（related_controllers / related_views / related_pages）
    _extractor = UseCaseExtractor(None)
    _extractor._enrich_controllers(usecases, routes)
    _extractor._enrich_pages(usecases, pages)

    # ---- エンティティ・リレーション ----
    info_gen = InformationModelGenerator(llm_provider=None)
    entities, relationships = info_gen.generate(models)

    # ---- ビジネスポリシー（.md からパース）----
    from extraction.derived.business_policy import CodeReference
    policies = []
    bp_path = output_dir / "rdra" / "business_policies.md"
    if bp_path.exists():
        bp_md = bp_path.read_text(encoding="utf-8")
        current_bp, current_cat = None, ""
        in_code_refs = False
        for line in bp_md.split("\n"):
            if line.startswith("## ") and not line.startswith("### ") and "全ポリシー" not in line and "サマリ" not in line:
                current_cat = line[3:].strip()
            m = re.match(r"### (BP-\d+): (.+)", line)
            if m:
                if current_bp:
                    policies.append(current_bp)
                current_bp = BusinessPolicy(id=m.group(1), name=m.group(2), category=current_cat, description="", related_entities=[], related_usecases=[], severity="must", code_references=[])
                in_code_refs = False
            elif current_bp:
                if line.startswith("- **重要度**:"):
                    current_bp.severity = {"必須": "must", "推奨": "should", "任意": "may"}.get(line.split(":", 1)[1].strip(), "must")
                    in_code_refs = False
                elif line.startswith("- **説明**:"):
                    current_bp.description = line.split(":", 1)[1].strip()
                    in_code_refs = False
                elif line.startswith("- **関連エンティティ**:"):
                    current_bp.related_entities = [e.strip() for e in line.split(":", 1)[1].split(",")]
                    in_code_refs = False
                elif line.startswith("- **関連ユースケース**:"):
                    current_bp.related_usecases = [u.strip() for u in line.split(":", 1)[1].split(",")]
                    in_code_refs = False
                elif line.startswith("- **コード参照**:"):
                    in_code_refs = True
                elif in_code_refs and line.strip().startswith("- `"):
                    ref_match = re.match(r"\s*- `(.+?)` — (.+?)(?:\s*\((\w+)\))?$", line)
                    if ref_match:
                        current_bp.code_references.append(CodeReference(
                            file_path=ref_match.group(1),
                            description=ref_match.group(2).strip(),
                            code_type=ref_match.group(3) or "",
                        ))
                elif not line.strip().startswith("- ") and not line.strip().startswith("  -"):
                    in_code_refs = False
        if current_bp:
            policies.append(current_bp)

    # ---- 状態遷移図（.md からパース）----
    state_machines = []
    st_path = output_dir / "rdra" / "state_transitions.md"
    if st_path.exists():
        st_md = st_path.read_text(encoding="utf-8")
        current_sm, in_states, in_transitions = None, False, False
        for line in st_md.split("\n"):
            m = re.match(r"## (.+?)（(.+?)\.(.+?)）", line)
            if m:
                if current_sm:
                    state_machines.append(current_sm)
                current_sm = EntityStateMachine(entity_name=m.group(1), entity_class=m.group(2), state_field=m.group(3))
                in_states, in_transitions = False, False
                continue
            if not current_sm:
                continue
            if "### 状態一覧" in line:
                in_states, in_transitions = True, False
                continue
            if "### 遷移一覧" in line:
                in_transitions, in_states = True, False
                continue
            if line.startswith("---"):
                in_states, in_transitions = False, False
                continue
            if in_states and line.startswith("|") and "状態" not in line and "---" not in line:
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if len(cols) >= 2:
                    current_sm.states.append(cols[0])
                    if cols[1] == "初期状態":
                        current_sm.initial_state = cols[0]
                    elif cols[1] == "終了状態":
                        current_sm.final_states.append(cols[0])
            if in_transitions and line.startswith("|") and "遷移元" not in line and "---" not in line:
                cols = [c.strip() for c in line.split("|")[1:-1]]
                if len(cols) >= 4:
                    current_sm.transitions.append(StateTransition(
                        entity_name=current_sm.entity_name,
                        from_state=cols[0], to_state=cols[1],
                        trigger=cols[2], guard=cols[3] if cols[3] != "-" else "",
                    ))
        if current_sm:
            state_machines.append(current_sm)

    # ---- Mermaid ソース構築 ----
    mermaid_sources = {}
    mermaid_sources["information_model"] = info_gen.to_mermaid(entities, relationships)
    groups = info_gen.group_by_usecase(entities, relationships, usecases)
    if groups:
        mermaid_sources["information_model_grouped"] = info_gen.to_mermaid_grouped(groups)
    uc_gen = UseCaseDiagramGenerator(None)
    mermaid_sources["usecase_diagram"] = uc_gen.generate_mermaid(usecases)
    mermaid_sources["usecase_conditions"] = uc_gen.generate_conditions_mermaid(usecases)
    for uc in usecases:
        mermaid_sources[f"uc_condition_{uc.id}"] = uc_gen.generate_single_condition_mermaid(uc)
    act_gen = ActivityDiagramGenerator()
    mermaid_sources["scenarios_overview"] = act_gen.generate_all_scenarios_flowchart(scenarios)
    uc_actor_map = {uc.id: uc.actor for uc in usecases}
    for sc in scenarios:
        actor_name = uc_actor_map.get(sc.usecase_id, "")
        mermaid_sources[f"scenario_{sc.scenario_id}"] = act_gen.generate_sequence_diagram(sc, actor_name=actor_name)
    st_gen = StateTransitionGenerator.__new__(StateTransitionGenerator)
    for sm in state_machines:
        mermaid_sources[f"state_{sm.entity_class}"] = st_gen.to_mermaid(sm)

    # ---- 画面仕様の読み込み（存在すれば）----
    screen_specs = []
    screen_path = output_dir / "usecases" / "screen_specs.json"
    if screen_path.exists():
        from extraction.screen_analyzer import ScreenAnalyzer
        screen_specs = ScreenAnalyzer.load_from_json(screen_path)

    # ---- ビューワー生成 ----
    config = _get_config()
    project_name = ", ".join(rp.name for rp in config.repo_paths) if config.repo_paths else ""
    renderer = MermaidRenderer(
        info_model_gen=info_gen,
        usecase_diagram_gen=uc_gen,
        activity_diagram_gen=act_gen,
        project_name=project_name,
    )
    rdra_dir = output_dir / "rdra"
    viewer_path = renderer._render_viewer(
        entities=entities, relationships=relationships,
        usecases=usecases, scenarios=scenarios,
        groups=groups, state_machines=state_machines,
        policies=policies, mermaid_sources=mermaid_sources,
        rdra_dir=rdra_dir,
        screen_specs=screen_specs,
    )
    return viewer_path


@app.command("viewer")
def run_viewer(
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ"
    ),
    port: int = typer.Option(
        8080, "--port", "-p", help="サーバーポート番号"
    ),
    no_open: bool = typer.Option(
        False, "--no-open", help="ブラウザを自動で開かない"
    ),
    regenerate: bool = typer.Option(
        False, "--regenerate", "-r", help="ビューワーHTMLを再生成してから起動"
    ),
):
    """
    RDRAビューワーをローカルサーバーで起動する。

    --regenerate で既存の解析結果からビューワーを再生成してから起動。
    """
    config = _get_config()
    output_dir = output_dir or config.output_dir
    output_dir = Path(output_dir)
    viewer_path = output_dir / "rdra" / "viewer.html"

    if regenerate or not viewer_path.exists():
        console.print("[dim]ビューワーを生成中...[/dim]")
        try:
            result_path = _build_viewer(output_dir)
            size_kb = Path(result_path).stat().st_size // 1024
            console.print(f"  -> {result_path} ({size_kb}KB)")
        except FileNotFoundError as e:
            console.print(f"[red]{e}[/red]")
            console.print("先に 'python main.py analyze' と 'python main.py rdra' を実行してください。")
            raise typer.Exit(1)

    if not viewer_path.exists():
        console.print(f"[red]ビューワーが見つかりません: {viewer_path}[/red]")
        raise typer.Exit(1)

    import http.server
    import functools
    import threading
    import webbrowser

    rdra_dir = str(output_dir / "rdra")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=rdra_dir)

    console.print(f"[green]RDRAビューワーを起動します[/green]")
    console.print(f"  URL: http://localhost:{port}/viewer.html")
    console.print(f"  終了: Ctrl+C")

    if not no_open:
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{port}/viewer.html")).start()

    try:
        with http.server.HTTPServer(("", port), handler) as httpd:
            httpd.serve_forever()
    except KeyboardInterrupt:
        console.print("\n[dim]サーバーを停止しました[/dim]")


@app.command("all")
def run_all(
    repo: Optional[list[str]] = typer.Option(
        None, "--repo", "-r", help="解析対象リポジトリのパス（複数指定可）"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ"
    ),
    parallel: int = typer.Option(
        0, "--parallel", "-j",
        help="リポジトリ並列度（0=自動: min(4, リポ数)、1=直列）"
    ),
):
    """
    全パートを順番に実行する。

    パート1（解析・UC抽出・画面分析）-> パート2（RDRAモデル）-> パート3（CRUDギャップ）。
    E2E 実行は loop-e2e へ委譲済み（スコープ外）。
    """
    _print_header("RDRA Analyzer - 全パート実行")

    config = _get_config()
    _apply_repo_option(config, repo)
    output_dir = output_dir or config.output_dir
    output_dir = Path(output_dir)

    try:
        config.validate()
    except ValueError as e:
        console.print(f"[red]設定エラー: {e}[/red]")
        raise typer.Exit(1)

    config.ensure_output_dirs()

    # パート1: ソースコード解析・UC抽出・画面分析
    console.print("\n" + "=" * 60)
    result = run_analyze.callback(
        repo=repo,
        output_dir=output_dir,
        max_routes=200,
        skip_llm=False,
        parallel=parallel,
    )
    if result is None:
        raise typer.Exit(1)
    usecases, screen_specs, routes, models = result

    # パート2: RDRAモデル生成
    console.print("\n" + "=" * 60)
    run_rdra.callback(repo=repo, input_file=None, output_dir=output_dir)

    # パート3: CRUDギャップ分析
    console.print("\n" + "=" * 60)
    run_gap.callback(repo=repo, input_file=None, output_dir=output_dir)

    console.print("\n" + "=" * 60)
    console.print(f"\n[bold green]全パート完了[/bold green]")
    console.print(f"  出力ディレクトリ: {output_dir}")
    console.print(f"  RDRAインデックス: {output_dir}/rdra/index.md")
    console.print(f"  CRUDギャップ: {output_dir}/gap/crud_gap_analysis.md")


def _load_analysis_result(data: dict):
    """
    JSONデータからユースケースと操作シナリオを復元する。
    """
    from extraction.usecase_extractor import UseCase
    from shared.scenario_builder import OperationScenario, OperationStep

    usecases = [
        UseCase(
            id=u["id"],
            name=u["name"],
            actor=u["actor"],
            description=u["description"],
            preconditions=u["preconditions"],
            postconditions=u["postconditions"],
            related_routes=u["related_routes"],
            related_pages=u.get("related_pages", []),
            related_entities=u["related_entities"],
            category=u["category"],
            priority=u.get("priority", "medium"),
            related_controllers=u.get("related_controllers", []),
            related_views=u.get("related_views", []),
        )
        for u in data.get("usecases", [])
    ]

    scenarios = [
        OperationScenario(
            usecase_id=s["usecase_id"],
            usecase_name=s["usecase_name"],
            scenario_id=s["scenario_id"],
            scenario_name=s["scenario_name"],
            scenario_type=s["scenario_type"],
            steps=[
                OperationStep(
                    step_no=st["step_no"],
                    actor=st["actor"],
                    action=st["action"],
                    expected_result=st["expected_result"],
                    ui_element=st.get("ui_element", ""),
                )
                for st in s.get("steps", [])
            ],
            variations=s.get("variations", []),
            frontend_url=s.get("frontend_url", ""),
            api_endpoint=s.get("api_endpoint", ""),
        )
        for s in data.get("scenarios", [])
    ]

    return usecases, scenarios


def _flow_base_dir(output_dir: Optional[Path]) -> Path:
    config = _get_config()
    return Path(output_dir or config.output_dir) / "usecases"


def _report_flow(result, success_msg: str) -> None:
    """業務フローコマンドの Result を表示する（workflows.md の UI マッピング）。"""
    from workflow.result import Ok

    if isinstance(result, Ok):
        console.print(f"[green]{success_msg}[/green]  -> 発行イベント: {result.value.kind}")
        return
    err = result.error
    name = type(err).__name__
    messages = {
        "NotPdM": "承認/FB/編集は PdM のみ操作できます",
        "IllegalTransition": "現在の状態ではその操作はできません",
        "NoConfirmedUsecases": "確定UCがありません。先に 'analyze' を確定してください",
        "UnknownUsecase": "指定されたUCが確定モデルにありません",
        "NotApproved": "引き渡しは承認後のみ可能です",
        "LoopE2eUnavailable": "loop-e2e へ接続できません。時間を置いて再試行してください",
    }
    console.print(f"[red]失敗: {messages.get(name, name)}[/red] ({err})")
    raise typer.Exit(1)


@flow_app.command("propose")
def flow_propose(
    flow_id: str = typer.Argument(..., help="業務フローID（例: BF-1）"),
    uc: Optional[list[str]] = typer.Option(None, "--uc", help="対象UC ID（省略時は確定UC全件）"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o", help="出力ディレクトリ"),
):
    """確定UC群から業務フローを想定する（System）。"""
    from workflow import service

    base = _flow_base_dir(output_dir)
    analysis_path = base / "analysis_result.json"
    if not analysis_path.exists():
        console.print("[red]analysis_result.json が見つかりません。先に 'analyze' を実行してください。[/red]")
        raise typer.Exit(1)
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
    confirmed = service.load_confirmed_uc_ids(analysis)
    uc_ids = tuple(uc) if uc else tuple(sorted(confirmed))
    _report_flow(service.propose(base, flow_id, uc_ids, confirmed), f"業務フロー {flow_id} を想定（UC {len(uc_ids)}件）")


@flow_app.command("review")
def flow_review(
    flow_id: str = typer.Argument(...),
    actor: str = typer.Option("PdM", "--actor"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """PdM がレビューに着手する。"""
    from workflow import service
    _report_flow(service.review(_flow_base_dir(output_dir), flow_id, actor), f"{flow_id} をレビュー")


@flow_app.command("feedback")
def flow_feedback(
    flow_id: str = typer.Argument(...),
    text: str = typer.Option(..., "--text", "-t", help="差し戻し理由"),
    actor: str = typer.Option("PdM", "--actor"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """PdM が差し戻す（→ 再想定待ち）。"""
    from workflow import service
    _report_flow(service.feedback(_flow_base_dir(output_dir), flow_id, actor, text), f"{flow_id} に FB")


@flow_app.command("approve")
def flow_approve(
    flow_id: str = typer.Argument(...),
    actor: str = typer.Option("PdM", "--actor"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """PdM が承認する（＝業務フロー確定）。"""
    from workflow import service
    _report_flow(service.approve(_flow_base_dir(output_dir), flow_id, actor), f"{flow_id} を承認")


@flow_app.command("handoff")
def flow_handoff(
    flow_id: str = typer.Argument(...),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """承認済みフローを loop-e2e へ引き渡す（PL 成果物を出力）。"""
    from workflow import service
    _report_flow(service.handoff(_flow_base_dir(output_dir), flow_id), f"{flow_id} を loop-e2e へ引き渡し")


@flow_app.command("status")
def flow_status(
    flow_id: str = typer.Argument(...),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """業務フローの現在状態を表示する。"""
    from workflow import service

    state = service.current_state(_flow_base_dir(output_dir), flow_id)
    if state is None:
        console.print(f"[yellow]{flow_id} は存在しません[/yellow]")
        raise typer.Exit(0)
    console.print(f"  {flow_id}: 状態 = {state.kind}")


if __name__ == "__main__":
    app()
