"""
テストコード生成モジュール

RDRA2.0 の業務フロー・利用シーンと、解析先ソースコードの情報を組み合わせて、
業務フロー/利用シーンに対応するテストコードを LLM で生成する。

テストは対象プロジェクトの言語・フレームワーク・テストフレームワークに合わせて
動的に生成される（例: PHPUnit, Jest, pytest, RSpec 等）。
"""

import json
from pathlib import Path
from dataclasses import dataclass, field

from llm.provider import LLMProvider
from analyzer.project_context import ProjectContext, build_context, format_context_for_prompt
from analyzer.source_parser import ParsedRoute, ParsedController, ParsedModel


SYSTEM_PROMPT = """\
あなたはテストエンジニアです。
RDRA2.0 の業務フロー/利用シーンに基づき、与えられたプロジェクトの言語・フレームワークに適した
テストコードを生成してください。

テストは以下を満たしてください:
- 対象プロジェクトで使用されているテストフレームワークを使う
- 業務フローの各ステップに対応するテストケースを含む
- API エンドポイントの呼び出し、レスポンスの検証を含む
- 日本語のコメントでステップとの対応を明記する
"""


@dataclass
class GeneratedTest:
    """生成されたテストコード"""
    source_id: str          # BUC-ID または利用シーン名
    source_name: str        # 業務フロー/利用シーン名
    source_type: str        # "business_flow" | "usage_scene"
    file_path: str          # 推奨ファイルパス
    language: str           # 言語名（PHP, TypeScript, Python 等）
    test_framework: str     # テストフレームワーク名
    code: str               # テストコード本体
    description: str = ""   # テストの説明


class TestCodeGenerator:
    """
    業務フロー・利用シーンからテストコードを生成するクラス。

    ソースコード解析結果（ルート、コントローラー、モデル）と
    プロジェクトコンテキスト（言語、フレームワーク）を活用して
    対象プロジェクトに適したテストコードを生成する。
    """

    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider

    def generate_from_flows(
        self,
        business_flows: list[dict],
        usage_scenes: list[dict],
        routes: list[ParsedRoute],
        controllers: list[ParsedController],
        models: list[ParsedModel],
        project_context: str,
        tech_stack: str = "",
    ) -> list[GeneratedTest]:
        """
        業務フロー・利用シーンからテストコードを生成する。

        Args:
            business_flows: 業務フロー一覧（dict形式）
            usage_scenes: 利用シーン一覧（dict形式）
            routes: 解析済みAPIルート
            controllers: 解析済みコントローラー
            models: 解析済みモデル
            project_context: プロジェクトコンテキスト文字列
            tech_stack: 技術スタック文字列

        Returns:
            list[GeneratedTest]: 生成されたテストコード一覧
        """
        results: list[GeneratedTest] = []

        route_summary = self._build_route_summary(routes)
        controller_summary = self._build_controller_summary(controllers)
        model_summary = self._build_model_summary(models)

        for flow in business_flows:
            test = self._generate_for_flow(
                flow, route_summary, controller_summary,
                model_summary, project_context, tech_stack,
            )
            if test:
                results.append(test)

        for scene in usage_scenes:
            test = self._generate_for_scene(
                scene, route_summary, controller_summary,
                model_summary, project_context, tech_stack,
            )
            if test:
                results.append(test)

        return results

    def _generate_for_flow(
        self,
        flow: dict,
        route_summary: str,
        controller_summary: str,
        model_summary: str,
        project_context: str,
        tech_stack: str,
    ) -> GeneratedTest | None:
        """1つの業務フローに対するテストコードを生成する"""
        steps_text = "\n".join(
            f"  {s['step_no']}. [{s['actor']}] {s['action']}"
            for s in flow.get("steps", [])
        )

        user_message = f"""\
## プロジェクト情報
{project_context}

技術スタック: {tech_stack}

## ソースコード構造

### APIルート
{route_summary}

### コントローラー/ハンドラー
{controller_summary}

### データモデル
{model_summary}

## 業務フロー
- BUC ID: {flow.get('buc_id', '')}
- BUC 名: {flow.get('buc_name', '')}
- ステップ:
{steps_text}

---

上記の業務フローに対応するテストコードを生成してください。

### 生成ルール
1. プロジェクトの言語・フレームワークに合ったテストフレームワークを使う
2. 業務フローの各ステップをテストメソッドまたはテストケースに対応させる
3. 実際のAPIルートに基づいてHTTPリクエストを構成する
4. データモデルに基づいてテストデータ（fixture/factory）を使う
5. 各テストメソッドに日本語コメントでステップ番号と内容を記載する

以下のJSON形式のみで返してください:
{{
  "file_path": "tests/Feature/OrderFlowTest.php",
  "language": "PHP",
  "test_framework": "PHPUnit",
  "description": "注文受付の業務フローテスト",
  "code": "<?php\\n\\nnamespace Tests\\\\Feature;\\n..."
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=16384,
            )
            return self._parse_test_response(
                response,
                source_id=flow.get("buc_id", ""),
                source_name=flow.get("buc_name", ""),
                source_type="business_flow",
            )
        except Exception:
            return None

    def _generate_for_scene(
        self,
        scene: dict,
        route_summary: str,
        controller_summary: str,
        model_summary: str,
        project_context: str,
        tech_stack: str,
    ) -> GeneratedTest | None:
        """1つの利用シーンに対するテストコードを生成する"""
        steps_text = ""
        for s in scene.get("steps", []):
            steps_text += f"  {s.get('step_no', '')}. [{s.get('actor', '')}] {s.get('action', '')}\n"

        user_message = f"""\
## プロジェクト情報
{project_context}

技術スタック: {tech_stack}

## ソースコード構造

### APIルート
{route_summary}

### コントローラー/ハンドラー
{controller_summary}

### データモデル
{model_summary}

## 利用シーン
- BUC ID: {scene.get('buc_id', '')}
- BUC 名: {scene.get('buc_name', '')}
- シーン名: {scene.get('scene_name', '')}
- 説明: {scene.get('description', '')}
- ステップ:
{steps_text}

---

上記の利用シーンに対応するテストコードを生成してください。

### 生成ルール
1. プロジェクトの言語・フレームワークに合ったテストフレームワークを使う
2. 利用シーンの各ステップをテストメソッドまたはテストケースに対応させる
3. 実際のAPIルートに基づいてHTTPリクエストを構成する
4. データモデルに基づいてテストデータ（fixture/factory）を使う
5. 各テストメソッドに日本語コメントでステップ番号と内容を記載する

以下のJSON形式のみで返してください:
{{
  "file_path": "tests/Feature/ProductSearchTest.php",
  "language": "PHP",
  "test_framework": "PHPUnit",
  "description": "商品検索の利用シーンテスト",
  "code": "<?php\\n\\nnamespace Tests\\\\Feature;\\n..."
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=16384,
            )
            return self._parse_test_response(
                response,
                source_id=scene.get("buc_id", ""),
                source_name=scene.get("scene_name", ""),
                source_type="usage_scene",
            )
        except Exception:
            return None

    def _parse_test_response(
        self, response: str,
        source_id: str, source_name: str, source_type: str,
    ) -> GeneratedTest | None:
        """LLMレスポンスからテストコードをパースする"""
        import re
        cleaned = re.sub(r"```(?:json)?\s*", "", response).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            return None

        try:
            data = json.loads(json_match.group(0))
        except json.JSONDecodeError:
            return None

        code = data.get("code", "")
        if not code:
            return None

        return GeneratedTest(
            source_id=source_id,
            source_name=source_name,
            source_type=source_type,
            file_path=data.get("file_path", ""),
            language=data.get("language", ""),
            test_framework=data.get("test_framework", ""),
            code=code,
            description=data.get("description", ""),
        )

    def _build_route_summary(self, routes: list[ParsedRoute]) -> str:
        if not routes:
            return "(なし)"
        lines = []
        for r in routes[:60]:
            mw = f" [{', '.join(r.middleware)}]" if r.middleware else ""
            lines.append(f"  {r.method:6s} {r.path}  -> {r.controller}.{r.action}{mw}")
        if len(routes) > 60:
            lines.append(f"  ... 他 {len(routes) - 60} 件")
        return "\n".join(lines)

    def _build_controller_summary(self, controllers: list[ParsedController]) -> str:
        if not controllers:
            return "(なし)"
        lines = []
        for c in controllers[:30]:
            methods = ", ".join(c.methods[:10])
            lines.append(f"  {c.class_name} ({c.file_path}): {methods}")
        return "\n".join(lines)

    def _build_model_summary(self, models: list[ParsedModel]) -> str:
        if not models:
            return "(なし)"
        lines = []
        for m in models[:30]:
            fields = ", ".join(m.fillable[:8])
            rels = ", ".join(m.relationships[:5]) if m.relationships else ""
            lines.append(f"  {m.class_name} ({m.table_name}): [{fields}] {rels}")
        return "\n".join(lines)


def save_generated_tests(
    tests: list[GeneratedTest], output_dir: Path,
) -> list[str]:
    """生成されたテストコードをファイルとして保存する"""
    saved: list[str] = []
    test_dir = output_dir / "generated_tests"
    test_dir.mkdir(parents=True, exist_ok=True)

    for test in tests:
        if not test.code:
            continue

        if test.file_path:
            # ディレクトリ構造を保持して保存
            rel_path = Path(test.file_path)
            file_path = test_dir / rel_path
        else:
            safe_name = test.source_name.replace(" ", "_").replace("/", "_")
            ext = _language_extension(test.language)
            file_path = test_dir / f"test_{safe_name}{ext}"

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(test.code, encoding="utf-8")
        saved.append(str(file_path))

    # サマリーMarkdownも出力
    if tests:
        summary = _build_summary_md(tests)
        summary_path = test_dir / "README.md"
        summary_path.write_text(summary, encoding="utf-8")
        saved.append(str(summary_path))

    return saved


def _language_extension(language: str) -> str:
    mapping = {
        "php": ".php", "python": ".py", "typescript": ".ts",
        "javascript": ".js", "ruby": ".rb", "go": ".go",
        "rust": ".rs", "java": ".java", "kotlin": ".kt",
        "elixir": ".exs", "dart": ".dart",
    }
    return mapping.get(language.lower(), ".txt")


def _build_summary_md(tests: list[GeneratedTest]) -> str:
    lines = [
        "# 生成テストコード一覧",
        "",
        "RDRA2.0 の業務フロー・利用シーンから自動生成されたテストコードです。",
        "",
        "| 種別 | BUC/シーン | ファイル | 言語 | フレームワーク |",
        "|------|-----------|---------|------|--------------|",
    ]
    for t in tests:
        kind = "業務フロー" if t.source_type == "business_flow" else "利用シーン"
        lines.append(
            f"| {kind} | {t.source_name} | {t.file_path} | "
            f"{t.language} | {t.test_framework} |"
        )
    lines.append("")
    return "\n".join(lines)
