"""
プロジェクトコンテキスト構築モジュール

対象リポジトリの CLAUDE.md / AGENTS.md / README.md およびマニフェストファイルを読み込み、
LLM プロンプトに注入するプロジェクトコンテキストを構築する。
これにより、言語・フレームワークに依存しない動的な解析を実現する。
"""

import subprocess
from pathlib import Path
from dataclasses import dataclass, field


# 読み込むドキュメントファイル（優先順）
CONTEXT_FILES = [
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
]

# 技術スタック検出用のマニフェストファイル
MANIFEST_FILES = {
    "package.json": "Node.js / JavaScript / TypeScript",
    "composer.json": "PHP",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "Gemfile": "Ruby",
    "pyproject.toml": "Python",
    "requirements.txt": "Python",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java / Kotlin (Gradle)",
    "build.gradle.kts": "Kotlin (Gradle)",
    "mix.exs": "Elixir",
    "pubspec.yaml": "Dart / Flutter",
    "Package.swift": "Swift",
    "CMakeLists.txt": "C / C++",
    "Makefile": "Make-based project",
    "deno.json": "Deno / TypeScript",
    "bun.lockb": "Bun / JavaScript / TypeScript",
}

# マニフェストファイルから読み取る最大バイト数
MAX_MANIFEST_BYTES = 2000

# コンテキストドキュメントの最大バイト数
MAX_CONTEXT_DOC_BYTES = 10000


@dataclass
class ProjectContext:
    """1つのリポジトリに関するコンテキスト情報"""
    repo_path: Path
    context_docs: dict[str, str] = field(default_factory=dict)
    detected_stacks: list[str] = field(default_factory=list)
    manifest_snippets: dict[str, str] = field(default_factory=dict)
    directory_tree: str = ""
    detected_frameworks: list[str] = field(default_factory=list)
    framework_knowledge: str = ""

    @property
    def has_claude_md(self) -> bool:
        return "CLAUDE.md" in self.context_docs

    @property
    def has_agents_md(self) -> bool:
        return "AGENTS.md" in self.context_docs


def build_context(repo_path: Path) -> ProjectContext:
    """
    リポジトリからプロジェクトコンテキストを構築する。

    Args:
        repo_path: リポジトリのルートディレクトリパス

    Returns:
        ProjectContext: 構築されたコンテキスト
    """
    ctx = ProjectContext(repo_path=repo_path)

    # 1. CLAUDE.md / AGENTS.md / README.md を読み込む
    ctx.context_docs = _read_context_docs(repo_path)

    # 2. マニフェストファイルから技術スタックを検出
    ctx.detected_stacks, ctx.manifest_snippets = _detect_tech_stacks(repo_path)

    # 3. フレームワーク知識を読み込む
    from knowledge.loader import detect_and_load
    ctx.detected_frameworks, ctx.framework_knowledge = detect_and_load(ctx.manifest_snippets)

    # 4. ディレクトリ構造をスナップショット
    ctx.directory_tree = _get_directory_tree(repo_path, max_depth=3)

    return ctx


def build_context_for_repos(repo_paths: list[Path]) -> list[ProjectContext]:
    """複数リポジトリのコンテキストを構築する"""
    return [build_context(p) for p in repo_paths]


def format_context_for_prompt(contexts: list[ProjectContext]) -> str:
    """
    プロジェクトコンテキストをLLMプロンプト用テキストに整形する。

    Args:
        contexts: ProjectContext のリスト

    Returns:
        str: LLMプロンプトに注入するテキスト
    """
    parts: list[str] = []

    for ctx in contexts:
        parts.append(f"# リポジトリ: {ctx.repo_path.name}")
        parts.append(f"パス: {ctx.repo_path}")
        parts.append("")

        # 技術スタック
        if ctx.detected_stacks:
            parts.append(f"## 技術スタック")
            for stack in ctx.detected_stacks:
                parts.append(f"- {stack}")
            parts.append("")

        # CLAUDE.md / AGENTS.md（最重要コンテキスト）
        for doc_name in ["CLAUDE.md", "AGENTS.md"]:
            if doc_name in ctx.context_docs:
                parts.append(f"## {doc_name} の内容")
                parts.append(ctx.context_docs[doc_name])
                parts.append("")

        # README.md（CLAUDE.md がない場合のみ）
        if "README.md" in ctx.context_docs and not ctx.has_claude_md:
            parts.append("## README.md の内容")
            parts.append(ctx.context_docs["README.md"])
            parts.append("")

        # フレームワーク知識（検出されたフレームワークの構成情報）
        if ctx.framework_knowledge:
            parts.append(f"## 検出されたフレームワーク: {', '.join(ctx.detected_frameworks)}")
            parts.append("")
            parts.append("以下はフレームワークの典型的なプロジェクト構成です。"
                         "ルート・モデル・コントローラー等を探す際の参考にしてください。")
            parts.append("")
            parts.append(ctx.framework_knowledge)
            parts.append("")

        # マニフェスト抜粋
        if ctx.manifest_snippets:
            parts.append("## マニフェストファイル抜粋")
            for fname, content in ctx.manifest_snippets.items():
                parts.append(f"### {fname}")
                parts.append(f"```")
                parts.append(content)
                parts.append(f"```")
            parts.append("")

        # ディレクトリ構造
        if ctx.directory_tree:
            parts.append("## ディレクトリ構造")
            parts.append(f"```")
            parts.append(ctx.directory_tree)
            parts.append(f"```")
            parts.append("")

    return "\n".join(parts)


def _read_context_docs(repo_path: Path) -> dict[str, str]:
    """CLAUDE.md, AGENTS.md, README.md を読み込む"""
    docs: dict[str, str] = {}

    for filename in CONTEXT_FILES:
        file_path = repo_path / filename
        if file_path.is_file():
            try:
                content = file_path.read_text(encoding="utf-8")
                # サイズ制限
                if len(content.encode("utf-8")) > MAX_CONTEXT_DOC_BYTES:
                    content = content[:MAX_CONTEXT_DOC_BYTES] + "\n...(truncated)"
                docs[filename] = content
            except Exception:
                continue

    return docs


def _detect_tech_stacks(repo_path: Path) -> tuple[list[str], dict[str, str]]:
    """マニフェストファイルから技術スタックを検出する"""
    stacks: list[str] = []
    snippets: dict[str, str] = {}

    for filename, stack_name in MANIFEST_FILES.items():
        file_path = repo_path / filename
        if file_path.is_file():
            stacks.append(f"{stack_name} ({filename})")
            try:
                content = file_path.read_text(encoding="utf-8")
                if len(content.encode("utf-8")) > MAX_MANIFEST_BYTES:
                    content = content[:MAX_MANIFEST_BYTES] + "\n...(truncated)"
                snippets[filename] = content
            except Exception:
                continue

    return stacks, snippets


def _get_directory_tree(repo_path: Path, max_depth: int = 3) -> str:
    """
    ディレクトリ構造を取得する。

    tree コマンドが利用可能な場合はそれを使い、
    なければ Python で簡易的に生成する。
    """
    try:
        result = subprocess.run(
            ["tree", "-L", str(max_depth), "-I",
             "node_modules|vendor|.git|__pycache__|.venv|venv|dist|build|target|.next"],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            # 行数制限
            lines = result.stdout.strip().split("\n")
            if len(lines) > 100:
                return "\n".join(lines[:100]) + "\n... (truncated)"
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # フォールバック: Python で簡易ツリー
    return _python_tree(repo_path, max_depth=max_depth)


def _python_tree(base: Path, max_depth: int, prefix: str = "", depth: int = 0) -> str:
    """Python での簡易ディレクトリツリー生成"""
    if depth >= max_depth:
        return ""

    IGNORE = {
        "node_modules", "vendor", ".git", "__pycache__", ".venv",
        "venv", "dist", "build", "target", ".next", ".cache",
    }

    lines: list[str] = []
    try:
        entries = sorted(base.iterdir(), key=lambda p: (not p.is_dir(), p.name))
    except PermissionError:
        return ""

    dirs = [e for e in entries if e.is_dir() and e.name not in IGNORE and not e.name.startswith(".")]
    files = [e for e in entries if e.is_file() and not e.name.startswith(".")]

    items = dirs + files
    for i, entry in enumerate(items[:50]):  # 各階層最大50エントリ
        connector = "|-- " if i < len(items) - 1 else "`-- "
        lines.append(f"{prefix}{connector}{entry.name}")

        if entry.is_dir():
            extension = "|   " if i < len(items) - 1 else "    "
            subtree = _python_tree(entry, max_depth, prefix + extension, depth + 1)
            if subtree:
                lines.append(subtree)

    return "\n".join(lines)
