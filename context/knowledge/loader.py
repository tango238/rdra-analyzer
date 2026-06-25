"""
フレームワーク知識ローダー

マニフェストファイルの内容からフレームワークを検出し、
該当する知識ファイルを読み込んでLLMプロンプト用テキストとして返す。
"""

from pathlib import Path

# このモジュールの親ディレクトリ = knowledge/
_KNOWLEDGE_DIR = Path(__file__).parent

# フレームワーク検出ルール:
# (マニフェストファイル名, 検索キーワード, フレームワークID)
_DETECTION_RULES: list[tuple[str, str, str]] = [
    # PHP
    ("composer.json", "laravel/framework", "laravel"),
    # Ruby
    ("Gemfile", "rails", "rails"),
    # Python
    ("requirements.txt", "django", "django"),
    ("pyproject.toml", "django", "django"),
    ("requirements.txt", "fastapi", "fastapi"),
    ("pyproject.toml", "fastapi", "fastapi"),
    # Java / Kotlin
    ("pom.xml", "spring-boot", "spring_boot"),
    ("build.gradle", "spring-boot", "spring_boot"),
    ("build.gradle.kts", "spring-boot", "spring_boot"),
    # JavaScript / TypeScript
    ("package.json", '"next"', "nextjs"),
    ("package.json", '"nuxt"', "nuxt"),
    ("package.json", '"express"', "express"),
    # Go
    ("go.mod", "gin-gonic/gin", "gin"),
    ("go.mod", "labstack/echo", "echo"),
    # Rust
    ("Cargo.toml", "actix-web", "actix"),
    # Elixir
    ("mix.exs", "phoenix", "phoenix"),
    # Dart
    ("pubspec.yaml", "flutter", "flutter"),
]


def detect_frameworks(manifest_snippets: dict[str, str]) -> list[str]:
    """
    マニフェストファイルの内容からフレームワークを検出する。

    Args:
        manifest_snippets: {ファイル名: 内容} のマッピング
                          （project_context の _detect_tech_stacks で取得済み）

    Returns:
        list[str]: 検出されたフレームワークIDのリスト（例: ["laravel", "nextjs"]）
    """
    detected: list[str] = []
    seen: set[str] = set()

    for manifest_file, keyword, framework_id in _DETECTION_RULES:
        if framework_id in seen:
            continue
        content = manifest_snippets.get(manifest_file, "")
        if keyword.lower() in content.lower():
            detected.append(framework_id)
            seen.add(framework_id)

    return detected


def load_knowledge(framework_ids: list[str]) -> str:
    """
    フレームワークIDに対応する知識ファイルを読み込んで結合する。

    Args:
        framework_ids: フレームワークIDのリスト（例: ["laravel", "nextjs"]）

    Returns:
        str: 結合された知識テキスト
    """
    parts: list[str] = []

    for fw_id in framework_ids:
        knowledge_file = _KNOWLEDGE_DIR / f"{fw_id}.md"
        if knowledge_file.is_file():
            try:
                content = knowledge_file.read_text(encoding="utf-8")
                parts.append(content)
            except Exception:
                continue

    return "\n\n---\n\n".join(parts)


def detect_and_load(manifest_snippets: dict[str, str]) -> tuple[list[str], str]:
    """
    マニフェストからフレームワークを検出し、知識を読み込む（一括操作）。

    Args:
        manifest_snippets: {ファイル名: 内容} のマッピング

    Returns:
        tuple[list[str], str]: (フレームワークIDリスト, 知識テキスト)
    """
    framework_ids = detect_frameworks(manifest_snippets)
    knowledge_text = load_knowledge(framework_ids)
    return framework_ids, knowledge_text
