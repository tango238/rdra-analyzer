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
from pathlib import Path
from typing import Optional

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
        from analyzer.project_context import build_context
        ctx = build_context(repo_path)
        if ctx.detected_frameworks:
            console.print(f"      [dim]フレームワーク: {', '.join(ctx.detected_frameworks)}[/dim]")


def _save_parse_checkpoint(data: dict, checkpoint_path: Path) -> None:
    """ソースコード解析の中間結果を保存する"""
    from analyzer.source_parser import ParsedRoute, ParsedController, ParsedModel, ParsedPage

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
                "call_chain": op.call_chain}

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
    from analyzer.source_parser import ParsedRoute, ParsedController, ParsedModel, ParsedPage, EntityOperation

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
    all_contexts = []
    completed_repos = set(checkpoint["completed_repos"]) if checkpoint else set()

    from analyzer.source_parser import SourceParser
    from analyzer.project_context import format_context_for_prompt, build_context
    parser = SourceParser(llm_provider=llm)

    for repo_path in config.repo_paths:
        repo_name = str(repo_path.name)

        # コンテキストは常に構築（再開時も必要）
        ctx = build_context(repo_path)
        all_contexts.append(ctx)

        if repo_name in completed_repos:
            console.print(f"  [dim]リポジトリ: {repo_name} (チェックポイントからスキップ)[/dim]")
            continue

        console.print(f"  [bold]リポジトリ: {repo_name}[/bold]")
        for ctx_file in ["CLAUDE.md", "AGENTS.md"]:
            if (repo_path / ctx_file).exists():
                console.print(f"    [dim]{ctx_file} を検出[/dim]")

        # 各ステップを個別に実行し、ステップごとに保存
        steps = [
            ("ルート", "routes"),
            ("コントローラー", "controllers"),
            ("モデル", "models"),
            ("ページ", "pages"),
        ]
        result = parser.parse_repo(repo_path)

        for step_name, key in steps:
            items = result[key]
            count = len(items)
            console.print(f"    -> {step_name}: {count}件")
            if key == "routes":
                all_routes.extend(items)
            elif key == "controllers":
                all_controllers.extend(items)
            elif key == "models":
                all_models.extend(items)
            elif key == "pages":
                all_pages.extend(items)

        if ctx.detected_stacks:
            console.print(f"    -> 技術スタック: {', '.join(ctx.detected_stacks)}")

        completed_repos.add(repo_name)

        # リポジトリごとにチェックポイント保存
        _save_parse_checkpoint({
            "routes": all_routes, "controllers": all_controllers,
            "models": all_models, "pages": all_pages,
            "completed_repos": list(completed_repos), "phase": "parse",
        }, checkpoint_path)
        console.print(f"    [dim]-> チェックポイント保存: {checkpoint_path}[/dim]")

    routes = all_routes[:max_routes]

    # チェックポイントを更新（ソースコード解析完了）
    _save_parse_checkpoint({
        "routes": all_routes, "controllers": all_controllers,
        "models": all_models, "pages": all_pages,
        "completed_repos": list(completed_repos), "phase": "parsed",
    }, checkpoint_path)

    # 画面分析（UC抽出の前に実行し、結果をUC抽出に活用）
    screen_specs = []
    screen_path = output_dir / "usecases" / "screen_specs.json"

    # 既存の画面仕様があれば読み込んでスキップ
    if resume and screen_path.exists():
        from analyzer.screen_analyzer import ScreenAnalyzer
        screen_specs = ScreenAnalyzer.load_from_json(screen_path)
        if screen_specs:
            console.print(f"\n  [cyan]既存の画面仕様 {len(screen_specs)}件を読み込み（スキップ）[/cyan]")

    if not screen_specs and all_pages and not skip_llm:
        console.print()
        _print_header("画面分析")
        from analyzer.source_parser import ParsedPage
        from analyzer.screen_analyzer import ScreenAnalyzer

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
        from analyzer.usecase_extractor import UsecaseExtractor
        extractor = UsecaseExtractor(None)
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
            from analyzer.usecase_extractor import UsecaseExtractor
            extractor = UsecaseExtractor(llm, project_context=project_context_text)

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
                from analyzer.scenario_builder import ScenarioBuilder
                builder = ScenarioBuilder(llm)
                builder.save_to_json(temp_usecases, [], output_path)
                console.print(f"    [dim]-> 中間保存: {output_path}[/dim]")

            usecases = extractor._deduplicate(usecases)
            usecases = extractor._assign_ids(usecases)
            console.print(f"  -> ユースケース: {len(usecases)}件（重複除去後）")

        # ユースケースを保存
        from analyzer.scenario_builder import ScenarioBuilder
        builder = ScenarioBuilder(llm)
        builder.save_to_json(usecases, [], output_path)
        console.print(f"  [dim]-> ユースケースを保存: {output_path}[/dim]")

    # チェックポイントを更新（フェーズ完了）
    _save_parse_checkpoint({
        "routes": all_routes, "controllers": all_controllers,
        "models": all_models, "pages": all_pages,
        "completed_repos": list(completed_repos), "phase": "done",
    }, checkpoint_path)

    console.print(f"\n[green]解析完了[/green]")
    console.print(f"  出力ファイル: {output_path}")

    return usecases, screen_specs, routes, all_models


@app.command("scenarios")
def run_scenarios(
    input_file: Optional[Path] = typer.Option(
        None, "--input", "-i", help="パート1の出力JSONファイル（省略時は ./output/usecases/analysis_result.json）"
    ),
    max_count: int = typer.Option(
        5, "--max", "-n", help="生成するシナリオ数の上限"
    ),
    offset: int = typer.Option(
        0, "--offset", help="スキップするユースケース数（再開用）"
    ),
):
    """
    パート1補助: 保存済みユースケースJSONからシナリオを追加生成する。

    analyze --no-scenarios 実行後に使用。
    中断しても中間保存されているので --offset で再開可能。
    """
    _print_header("シナリオ生成（保存済みユースケースから）")

    config = _get_config()
    input_file = input_file or Path(config.output_dir) / "usecases" / "analysis_result.json"

    if not input_file.exists():
        console.print(f"[red]入力ファイルが見つかりません: {input_file}[/red]")
        console.print("先に 'python main.py analyze --no-scenarios' を実行してください。")
        raise typer.Exit(1)

    data = json.loads(input_file.read_text(encoding="utf-8"))
    usecases, existing_scenarios = _load_analysis_result(data)
    console.print(f"  読み込み: ユースケース {len(usecases)}件 | 既存シナリオ {len(existing_scenarios)}件")

    target = usecases[offset: offset + max_count]
    if not target:
        console.print("[yellow]処理対象のユースケースがありません（--offset を確認）[/yellow]")
        raise typer.Exit(0)

    llm = _get_llm()

    # 画面仕様を読み込み（存在すれば）
    screen_specs = []
    screen_path = (input_file.parent if input_file else Path(config.output_dir) / "usecases") / "screen_specs.json"
    if screen_path.exists():
        from analyzer.screen_analyzer import ScreenAnalyzer
        screen_specs = ScreenAnalyzer.load_from_json(screen_path)
        console.print(f"  画面仕様: {len(screen_specs)}件を読み込み")

    from analyzer.scenario_builder import ScenarioBuilder
    builder = ScenarioBuilder(llm, screen_specs=screen_specs)

    new_scenarios = list(existing_scenarios)
    validated_count = 0
    retried_count = 0
    for i, uc in enumerate(target):
        console.print(f"  [{offset+i+1}/{len(usecases)}] {uc.id}: {uc.name}")
        if screen_specs:
            sc_list = builder.build_and_validate_for_usecase(uc)
            # 検証結果をログ出力
            from analyzer.scenario_verifier import ScenarioVerifier
            verifier = ScenarioVerifier()
            matched_screens = builder._find_screens_for_usecase(uc)
            if matched_screens:
                validated_count += 1
                all_labels = set()
                for screen in matched_screens:
                    for b in screen.action_buttons:
                        all_labels.add(b.label)
                    for f in screen.form_fields:
                        all_labels.add(f.label)
                    for m in screen.shared_nav_items:
                        all_labels.add(m.label)
                    for modal in screen.modals:
                        all_labels.add(modal)
                    for tab in screen.tabs:
                        all_labels.add(tab)
                has_issues = False
                for sc in sc_list:
                    for step in sc.steps:
                        if step.actor == "システム":
                            continue
                        issues = verifier._verify_step(
                            step, sc.scenario_id,
                            all_labels, set(), set(), set(), matched_screens,
                        )
                        if issues:
                            has_issues = True
                            break
                if not has_issues:
                    console.print(f"    [green]✓ 画面検証OK[/green]")
                else:
                    retried_count += 1
                    console.print(f"    [yellow]△ 一部不整合あり（再生成済み）[/yellow]")
        else:
            sc_list = builder._build_for_usecase(uc)
        new_scenarios.extend(sc_list)
        builder.save_to_json(usecases, new_scenarios, input_file)

    console.print(f"\n[green]シナリオ追加完了[/green]")
    console.print(f"  合計シナリオ数: {len(new_scenarios)}件")
    if screen_specs:
        console.print(f"  画面検証: {validated_count}件検証 | {retried_count}件再生成")
    console.print(f"  出力ファイル: {input_file}")
    if offset + max_count < len(usecases):
        next_offset = offset + max_count
        console.print(
            f"  [dim]続きを生成するには: python main.py scenarios --offset {next_offset}[/dim]"
        )


@app.command("verify")
def run_verify(
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ"
    ),
    fix: bool = typer.Option(
        False, "--fix", help="LLMで不整合シナリオを自動修正する"
    ),
):
    """
    シナリオ×画面 突き合わせ検証

    操作シナリオの各ステップが実際の画面UI要素と整合しているか検証する。
    --fix を指定すると、不整合のあるシナリオをLLMで自動修正する。
    """
    _print_header("シナリオ×画面 突き合わせ検証")

    config = _get_config()
    output_dir = output_dir or config.output_dir
    output_dir = Path(output_dir)

    # 解析結果の読み込み
    analysis_path = output_dir / "usecases" / "analysis_result.json"
    if not analysis_path.exists():
        console.print("[red]解析結果が見つかりません。先に 'analyze' を実行してください。[/red]")
        raise typer.Exit(1)

    data = json.loads(analysis_path.read_text(encoding="utf-8"))
    usecases, scenarios = _load_analysis_result(data)
    console.print(f"  ユースケース: {len(usecases)}件 | シナリオ: {len(scenarios)}件")

    # 画面仕様の読み込み
    screen_path = output_dir / "usecases" / "screen_specs.json"
    if not screen_path.exists():
        console.print("[red]画面仕様が見つかりません。先に 'screens' を実行してください。[/red]")
        raise typer.Exit(1)

    from analyzer.screen_analyzer import ScreenAnalyzer
    screen_specs = ScreenAnalyzer.load_from_json(screen_path)
    console.print(f"  画面仕様: {len(screen_specs)}件")

    # 検証実行
    from analyzer.scenario_verifier import ScenarioVerifier
    from analyzer.scenario_builder import ScenarioBuilder
    llm = _get_llm() if fix else None

    # 中間保存コールバック
    def _save_progress(fixed_so_far, remaining):
        all_scenarios = fixed_so_far + remaining
        builder = ScenarioBuilder(llm)
        builder.save_to_json(usecases, all_scenarios, analysis_path)
        console.print(f"    [dim]-> 中間保存: {len(fixed_so_far)}件修正済み[/dim]")

    verifier = ScenarioVerifier(llm, save_callback=_save_progress if fix else None)

    console.print("[dim]検証中...[/dim]")
    results = verifier.verify_all(scenarios, screen_specs, usecases)

    # サマリ表示
    total = len(results)
    with_issues = sum(1 for r in results if r.issues)
    total_issues = sum(len(r.issues) for r in results)
    avg_pass = sum(r.pass_rate for r in results) / total if total else 0

    console.print(f"\n[bold]検証結果:[/bold]")
    console.print(f"  シナリオ数: {total}")
    console.print(f"  問題あり: {with_issues}件")
    console.print(f"  総問題数: {total_issues}")
    console.print(f"  平均適合率: {avg_pass:.0%}")

    # 問題の内訳
    issue_types: dict[str, int] = {}
    for r in results:
        for i in r.issues:
            issue_types[i.issue_type] = issue_types.get(i.issue_type, 0) + 1
    if issue_types:
        console.print("\n  [bold]問題内訳:[/bold]")
        type_labels = {
            "missing_element": "存在しないUI要素",
            "no_matching_screen": "対応画面なし",
            "wrong_label": "ラベル不一致",
            "missing_api": "API未対応",
        }
        for t, count in sorted(issue_types.items(), key=lambda x: -x[1]):
            console.print(f"    {type_labels.get(t, t)}: {count}件")

    # レポート保存
    report_path = output_dir / "usecases" / "verification_report"
    ScenarioVerifier.save_report(results, report_path)
    console.print(f"\n  レポート: {report_path}.json / {report_path}.md")

    # 自動修正
    if fix and with_issues > 0:
        # 前回修正済みのシナリオを検出（中間保存から再開）
        # 再検証して問題なしのシナリオ = 前回修正済み
        already_fixed = set()
        for r in results:
            if not r.issues:
                # 問題なし = 元から正常 or 前回修正済み
                # 初回検証レポートと比較して、以前問題ありだったが今は正常なものを特定
                already_fixed.add(r.scenario_id)
        # ただし初回実行時は全て「問題なし=元から正常」なのでスキップ対象にはならない
        # already_fixed から元々問題なしだったものを除外
        originally_ok = {r.scenario_id for r in results if not r.issues}
        # 再開用: 問題ありシナリオのみが修正対象
        # already_fixed は使わず、前回の検証レポートから判定
        report_json_path = output_dir / "usecases" / "verification_report.json"
        previously_fixed = set()
        if report_json_path.exists():
            prev_report = json.loads(report_json_path.read_text(encoding="utf-8"))
            prev_issue_ids = {r["scenario_id"] for r in prev_report.get("results", []) if r.get("issues")}
            # 前回問題ありだが今回問題なし → 修正済み
            for r in results:
                if r.scenario_id in prev_issue_ids and not r.issues:
                    previously_fixed.add(r.scenario_id)
            if previously_fixed:
                console.print(f"  [cyan]前回修正済み: {len(previously_fixed)}件をスキップ[/cyan]")

        remaining = with_issues - len(previously_fixed & {r.scenario_id for r in results if r.issues})
        console.print(f"\n[dim]不整合シナリオを修正中（{remaining}件）...[/dim]")
        fixed_scenarios = verifier.fix_scenarios(
            scenarios, screen_specs, usecases, results,
            already_fixed=previously_fixed,
        )

        # 修正後のシナリオを保存
        builder = ScenarioBuilder(llm)
        builder.save_to_json(usecases, fixed_scenarios, analysis_path)
        console.print(f"  -> 修正済みシナリオを保存: {analysis_path}")

        # 再検証
        console.print("[dim]再検証中...[/dim]")
        results2 = verifier.verify_all(fixed_scenarios, screen_specs, usecases)
        with_issues2 = sum(1 for r in results2 if r.issues)
        avg_pass2 = sum(r.pass_rate for r in results2) / len(results2) if results2 else 0
        console.print(f"  修正後: 問題あり {with_issues} → {with_issues2}件 | 適合率 {avg_pass:.0%} → {avg_pass2:.0%}")

    console.print(f"\n[green]検証完了[/green]")


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

    from analyzer.source_parser import ParsedPage
    cp = json.loads(cp_path.read_text(encoding="utf-8"))
    pages = [ParsedPage(**p) for p in cp.get("pages", [])]
    console.print(f"  ページ数: {len(pages)}件")

    if not pages:
        console.print("[yellow]解析済みページがありません。[/yellow]")
        raise typer.Exit(0)

    llm = _get_llm()
    from analyzer.screen_analyzer import ScreenAnalyzer
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
    from analyzer.project_context import build_context, format_context_for_prompt
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

    from analyzer.source_parser import ParsedRoute, ParsedController, ParsedModel
    models = [ParsedModel(**m) if isinstance(m, dict) else m for m in cp["models"]]
    all_routes = [ParsedRoute(**r) if isinstance(r, dict) else r for r in cp["routes"]]
    all_controllers = [ParsedController(**c) if isinstance(c, dict) else c for c in cp["controllers"]]
    console.print(f"  チェックポイントから読み込み: ルート {len(all_routes)}件 | コントローラー {len(all_controllers)}件 | モデル {len(models)}件")

    # プロジェクトコンテキスト構築
    project_context_text = ""
    if config.repo_paths:
        from analyzer.project_context import build_context, format_context_for_prompt
        all_contexts = [build_context(rp) for rp in config.repo_paths]
        project_context_text = format_context_for_prompt(all_contexts)

    llm = _get_llm()

    # 情報モデル生成
    console.print("[dim]情報モデルを生成中...[/dim]")
    from rdra.information_model import InformationModelGenerator
    info_gen = InformationModelGenerator(llm, project_context=project_context_text)
    entities, relationships = info_gen.generate(models)
    console.print(f"  -> エンティティ: {len(entities)}件 | リレーション: {len(relationships)}件")

    # ユースケース複合図・アクティビティ図・状態遷移図・ビジネスポリシーの生成と保存
    from rdra.usecase_diagram import UsecaseDiagramGenerator
    from rdra.activity_diagram import ActivityDiagramGenerator
    from rdra.state_transition import StateTransitionGenerator
    from rdra.business_policy import BusinessPolicyExtractor
    from rdra.mermaid_renderer import MermaidRenderer

    state_gen = StateTransitionGenerator(llm, project_context=project_context_text)
    bp_ext = BusinessPolicyExtractor(llm, project_context=project_context_text)

    # プロジェクト名をリポジトリ名から取得
    project_name = ", ".join(rp.name for rp in config.repo_paths) if config.repo_paths else ""

    renderer = MermaidRenderer(
        info_model_gen=info_gen,
        usecase_diagram_gen=UsecaseDiagramGenerator(llm),
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
    )

    console.print(f"\n[green]RDRAモデル生成完了[/green]")
    console.print(f"  生成ファイル数: {len(saved_files)}")
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

    from analyzer.source_parser import ParsedRoute, ParsedModel, EntityOperation
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
        from analyzer.project_context import build_context, format_context_for_prompt
        all_contexts = [build_context(rp) for rp in config.repo_paths]
        project_context_text = format_context_for_prompt(all_contexts)

    # エンティティ生成（LLMなしで実行）
    from rdra.information_model import InformationModelGenerator
    info_gen = InformationModelGenerator(None, project_context=project_context_text)
    entities, _ = info_gen.generate(models)

    # CRUDギャップ分析
    console.print("[dim]CRUDギャップを分析中...[/dim]")
    from gap.crud_analyzer import CrudAnalyzer
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


@app.command("e2e")
def run_e2e(
    input_file: Optional[Path] = typer.Option(
        None, "--input", "-i", help="パート1の出力JSONファイル"
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o", help="出力ディレクトリ"
    ),
    base_url: Optional[str] = typer.Option(
        None, "--url", "-u", help="テスト対象のベースURL"
    ),
    headless: bool = typer.Option(
        True, "--headless/--no-headless", help="ヘッドレスモード"
    ),
    scenario_filter: Optional[str] = typer.Option(
        None, "--filter", "-f", help="実行するシナリオIDのプレフィックス（例: UC-001）"
    ),
    normal_only: bool = typer.Option(
        False, "--normal-only", help="正常系シナリオのみ実行"
    ),
):
    """
    パート4: E2Eテスト実行

    操作シナリオをPlaywrightで自動実行する。
    エラー時はエージェントループでリカバリーを試みる。
    """
    _print_header("パート4: E2Eテスト実行")

    config = _get_config()
    output_dir = output_dir or Path(config.output_dir) / "e2e"

    if base_url:
        config.e2e_base_url = base_url
    config.e2e_headless = headless

    input_file = input_file or (config.output_dir / "usecases" / "analysis_result.json")
    if not input_file.exists():
        console.print("[yellow]解析結果が見つかりません。先に 'analyze' コマンドを実行してください。[/yellow]")
        raise typer.Exit(1)

    data = json.loads(Path(input_file).read_text(encoding="utf-8"))
    _, scenarios = _load_analysis_result(data)

    if scenario_filter:
        scenarios = [s for s in scenarios if s.usecase_id.startswith(scenario_filter)]
        console.print(f"フィルター適用: {scenario_filter} -> {len(scenarios)}件")

    if normal_only:
        scenarios = [s for s in scenarios if s.scenario_type == "normal"]
        console.print(f"正常系のみ: {len(scenarios)}件")

    llm = _get_llm()

    from e2e.scenario_executor import ScenarioExecutor
    executor = ScenarioExecutor(llm)
    results = executor.run_all(scenarios, Path(output_dir))

    console.print(f"\n[green]E2Eテスト完了[/green]")
    console.print(f"  結果: {output_dir}/e2e_results.md")


def _build_viewer(output_dir: Path) -> str:
    """既存の解析結果・RDRAモデルからビューワーHTMLを再生成する"""
    import re
    from rdra.information_model import InformationModelGenerator
    from rdra.mermaid_renderer import MermaidRenderer
    from rdra.usecase_diagram import UsecaseDiagramGenerator
    from rdra.activity_diagram import ActivityDiagramGenerator
    from rdra.state_transition import StateTransitionGenerator, EntityStateMachine, StateTransition
    from rdra.business_policy import BusinessPolicy
    from analyzer.usecase_extractor import UsecaseExtractor
    from analyzer.source_parser import ParsedModel, ParsedRoute

    # ---- ユースケース・シナリオ読み込み ----
    analysis_path = output_dir / "usecases" / "analysis_result.json"
    if not analysis_path.exists():
        raise FileNotFoundError(f"解析結果が見つかりません: {analysis_path}")
    data = json.loads(analysis_path.read_text(encoding="utf-8"))
    usecases, scenarios = _load_analysis_result(data)

    # ---- チェックポイントからモデル・ルート読み込み ----
    cp_path = output_dir / "usecases" / "_checkpoint.json"
    models, routes = [], []
    if cp_path.exists():
        cp = json.loads(cp_path.read_text(encoding="utf-8"))
        models = [ParsedModel(**m) for m in cp.get("models", [])]
        routes = [ParsedRoute(**r) for r in cp.get("routes", [])]

    # コントローラー紐付け
    UsecaseExtractor(None)._enrich_controllers(usecases, routes)

    # ---- エンティティ・リレーション ----
    info_gen = InformationModelGenerator(llm_provider=None)
    entities, relationships = info_gen.generate(models)

    # ---- ビジネスポリシー（.md からパース）----
    from rdra.business_policy import CodeReference
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
    uc_gen = UsecaseDiagramGenerator(None)
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
        from analyzer.screen_analyzer import ScreenAnalyzer
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
    skip_e2e: bool = typer.Option(
        False, "--skip-e2e", help="E2Eテストをスキップ"
    ),
    base_url: Optional[str] = typer.Option(
        None, "--url", "-u", help="E2EテストのベースURL"
    ),
):
    """
    全パートを順番に実行する。

    パート1 -> パート2 -> パート3 -> パート4 の順に実行。
    E2Eテストをスキップする場合は --skip-e2e を指定。
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

    # パート4: E2Eテスト
    if not skip_e2e:
        console.print("\n" + "=" * 60)
        run_e2e.callback(
            input_file=None,
            output_dir=output_dir / "e2e",
            base_url=base_url,
            headless=True,
            scenario_filter=None,
            normal_only=True,
        )
    else:
        console.print("\n[yellow]E2Eテストをスキップしました[/yellow]")

    console.print("\n" + "=" * 60)
    console.print(f"\n[bold green]全パート完了[/bold green]")
    console.print(f"  出力ディレクトリ: {output_dir}")
    console.print(f"  RDRAインデックス: {output_dir}/rdra/index.md")
    console.print(f"  CRUDギャップ: {output_dir}/gap/crud_gap_analysis.md")


def _load_analysis_result(data: dict):
    """
    JSONデータからユースケースと操作シナリオを復元する。
    """
    from analyzer.usecase_extractor import Usecase
    from analyzer.scenario_builder import OperationScenario, OperationStep

    usecases = [
        Usecase(
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


if __name__ == "__main__":
    app()
