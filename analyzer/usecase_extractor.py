"""
LLMを使用したユースケース抽出モジュール

ソースコード解析結果（APIルート・コントローラー・ページ）をもとに
Claude API でユースケースを抽出・構造化する。

プロジェクトコンテキスト（CLAUDE.md / AGENTS.md 由来）を動的に注入し、
どんな言語・フレームワークにも対応する。
"""

import json
import re
from dataclasses import dataclass, field

from llm.provider import LLMProvider
from .source_parser import ParsedRoute, ParsedController, ParsedModel, ParsedPage


@dataclass
class Usecase:
    """抽出されたユースケース"""
    id: str                     # UC-001 などの識別子
    name: str                   # ユースケース名（日本語）
    actor: str                  # アクター（管理者・ユーザーなど）
    description: str            # 概要説明
    preconditions: list[str]    # 事前条件
    postconditions: list[str]   # 事後条件
    related_routes: list[str]   # 関連APIルート
    related_pages: list[str]    # 関連フロントエンドページ
    related_entities: list[str] # 関連エンティティ（モデル）
    category: str               # カテゴリ（ユーザー管理・商品管理など）
    priority: str = "medium"    # 優先度（high/medium/low）
    related_controllers: list[str] = field(default_factory=list)  # 関連コントローラー
    related_views: list[str] = field(default_factory=list)        # 関連ビュー/ページコンポーネント


class UsecaseExtractor:
    """
    LLMを使ってAPIルートとページ情報からユースケースを抽出するクラス。

    プロジェクトコンテキスト（CLAUDE.md 由来）を活用して、
    プロジェクト固有のドメイン知識・アクター・カテゴリを動的に推定する。
    """

    BATCH_SIZE = 30

    def __init__(self, llm_provider: LLMProvider, project_context: str = ""):
        """
        Args:
            llm_provider: LLM プロバイダー
            project_context: プロジェクトコンテキスト文字列（CLAUDE.md 等から構築）
        """
        self._llm = llm_provider
        self._project_context = project_context

    def extract(
        self,
        routes: list[ParsedRoute],
        controllers: list[ParsedController],
        models: list[ParsedModel],
        pages: list[ParsedPage],
    ) -> list[Usecase]:
        """
        解析結果からユースケースを抽出する。

        Args:
            routes: 解析されたAPIルート一覧
            controllers: 解析されたコントローラー一覧
            models: 解析されたモデル一覧
            pages: 解析されたページ一覧

        Returns:
            list[Usecase]: 抽出されたユースケース一覧
        """
        context = self._build_context(controllers, models, pages)

        usecases: list[Usecase] = []
        route_batches = self._split_into_batches(routes, self.BATCH_SIZE)

        for batch_idx, batch in enumerate(route_batches):
            batch_usecases = self._extract_batch(
                batch, context, batch_idx, len(route_batches)
            )
            usecases.extend(batch_usecases)

        usecases = self._deduplicate(usecases)
        usecases = self._assign_ids(usecases)

        # ルートからコントローラー・ページを自動紐付け
        self._enrich_controllers(usecases, routes)
        self._enrich_pages(usecases, pages)

        return usecases

    def _build_context(
        self,
        controllers: list[ParsedController],
        models: list[ParsedModel],
        pages: list[ParsedPage],
        screen_specs: list = None,
    ) -> str:
        """
        LLMへのコンテキスト情報を構築する。
        CLAUDE.md / AGENTS.md 由来のプロジェクトコンテキストを基盤とし、
        解析済みのモデル・ページ情報・画面仕様で補完する。
        """
        parts: list[str] = []

        # プロジェクトコンテキスト（CLAUDE.md 等）を最優先で注入
        if self._project_context:
            parts.append("# プロジェクトコンテキスト")
            parts.append(self._project_context)
            parts.append("")

        # モデル名一覧
        model_names = [m.class_name for m in models[:50]]
        if model_names:
            parts.append(f"## エンティティ/モデル")
            parts.append(", ".join(model_names))
            parts.append("")

        # ページ情報
        if pages:
            page_lines: list[str] = []
            for p in pages[:40]:
                line = f"  {p.route_path}"
                if p.imported_hooks:
                    line += f" [hooks: {', '.join(p.imported_hooks[:3])}]"
                if p.form_fields:
                    line += f" [fields: {', '.join(p.form_fields[:5])}]"
                if p.api_calls:
                    line += f" [api: {', '.join(p.api_calls[:2])}]"
                page_lines.append(line)
            parts.append("## ページ/ビュー")
            parts.append("\n".join(page_lines))
            parts.append("")

        # 画面仕様（画面分析の結果）
        if screen_specs:
            screen_lines: list[str] = []
            for spec in screen_specs[:50]:
                line = f"  {spec.route_path}: {spec.page_title or '(無題)'}"
                if spec.action_buttons:
                    btn_names = [b.label for b in spec.action_buttons[:5]]
                    if btn_names:
                        line += f" [ボタン: {', '.join(btn_names)}]"
                if spec.form_fields:
                    field_names = [f.label for f in spec.form_fields[:5]]
                    if field_names:
                        line += f" [フォーム: {', '.join(field_names)}]"
                if spec.modals:
                    line += f" [モーダル: {', '.join(spec.modals[:3])}]"
                if spec.tabs:
                    line += f" [タブ: {', '.join(spec.tabs[:5])}]"
                screen_lines.append(line)
            parts.append("## 画面仕様（UI要素）")
            parts.append("\n".join(screen_lines))
            parts.append("")

        return "\n".join(parts)

    def _split_into_batches(
        self, routes: list[ParsedRoute], batch_size: int
    ) -> list[list[ParsedRoute]]:
        """ルートリストをバッチに分割する"""
        return [
            routes[i:i + batch_size]
            for i in range(0, len(routes), batch_size)
        ]

    def _extract_batch(
        self,
        routes: list[ParsedRoute],
        context: str,
        batch_idx: int,
        total_batches: int,
    ) -> list[Usecase]:
        """1バッチのルートからユースケースを抽出する"""
        routes_text = self._format_routes(routes)

        system_prompt = """あなたはRDRA（Relationship-Driven Requirements Analysis）の専門家です。
APIルートとプロジェクト情報を分析して、ユースケースを抽出してください。

以下のJSON形式で回答してください（コードブロック不要）:
{
  "usecases": [
    {
      "name": "ユースケース名（日本語）",
      "actor": "アクター名",
      "description": "概要説明",
      "preconditions": ["事前条件1", "事前条件2"],
      "postconditions": ["事後条件1"],
      "related_routes": ["GET /users", "POST /users"],
      "related_entities": ["User", "Profile"],
      "category": "カテゴリ名",
      "priority": "high|medium|low"
    }
  ]
}

ルールと指示:
- 複数の関連ルートを1つのユースケースにまとめる（例: CRUD操作は1つの「管理」ユースケースに）
- アクター名はプロジェクトコンテキストから推定する（不明な場合は「ユーザー」「管理者」「システム」を使用）
- カテゴリは業務ドメインで分類する
- 日本語で出力する"""

        user_message = f"""
{context}

## 解析対象APIルート（バッチ {batch_idx + 1}/{total_batches}）

{routes_text}

上記のAPIルートからユースケースを抽出してください。
"""

        response = self._llm.complete_simple(
            user_message=user_message,
            system_prompt=system_prompt,
        )

        return self._parse_response(response, routes)

    def _format_routes(self, routes: list[ParsedRoute]) -> str:
        """ルートリストをLLMへの入力テキストに整形する"""
        lines = []
        for route in routes:
            mw_str = ", ".join(route.middleware) if route.middleware else "なし"
            lines.append(
                f"- {route.method:7} {route.path:<50} "
                f"[{route.controller}] middleware={mw_str}"
            )
        return "\n".join(lines)

    def _parse_response(
        self, response: str, routes: list[ParsedRoute]
    ) -> list[Usecase]:
        """LLMのレスポンスをパースしてUsecaseオブジェクトに変換する"""
        usecases: list[Usecase] = []

        cleaned = re.sub(r"```(?:json)?\s*", "", response).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
            for item in data.get("usecases", []):
                usecases.append(Usecase(
                    id="",
                    name=item.get("name", "不明なユースケース"),
                    actor=item.get("actor", "ユーザー"),
                    description=item.get("description", ""),
                    preconditions=item.get("preconditions", []),
                    postconditions=item.get("postconditions", []),
                    related_routes=item.get("related_routes", []),
                    related_pages=item.get("related_pages", []),
                    related_entities=item.get("related_entities", []),
                    category=item.get("category", "その他"),
                    priority=item.get("priority", "medium"),
                ))
        except (json.JSONDecodeError, KeyError):
            usecases = self._fallback_extraction(routes)

        return usecases

    def _fallback_extraction(self, routes: list[ParsedRoute]) -> list[Usecase]:
        """LLMパース失敗時のフォールバック"""
        groups: dict[str, list[ParsedRoute]] = {}
        for route in routes:
            # コントローラー名からエンティティ部分を抽出
            entity = re.sub(
                r"(Controller|Handler|Service|Resource|View)$",
                "", route.controller
            )
            if not entity:
                entity = route.controller or "Unknown"
            groups.setdefault(entity, []).append(route)

        usecases = []
        for entity, entity_routes in groups.items():
            methods = [r.method for r in entity_routes]
            name = f"{entity}管理"
            usecases.append(Usecase(
                id="",
                name=name,
                actor="ユーザー",
                description=f"{entity}の管理操作（{', '.join(set(methods))}）",
                preconditions=["認証済みであること"],
                postconditions=[],
                related_routes=[f"{r.method} {r.path}" for r in entity_routes],
                related_pages=[],
                related_entities=[entity],
                category="管理",
                priority="medium",
            ))
        return usecases

    def _deduplicate(self, usecases: list[Usecase]) -> list[Usecase]:
        """同名のユースケースを重複除去する"""
        seen: set[str] = set()
        result: list[Usecase] = []
        for uc in usecases:
            if uc.name not in seen:
                seen.add(uc.name)
                result.append(uc)
        return result

    def _assign_ids(self, usecases: list[Usecase]) -> list[Usecase]:
        """ユースケースにUC-001形式のIDを振る"""
        for i, uc in enumerate(usecases, start=1):
            uc.id = f"UC-{i:03d}"
        return usecases

    def _enrich_controllers(
        self, usecases: list[Usecase], routes: list[ParsedRoute]
    ) -> None:
        """related_routes からコントローラーを自動紐付けする"""
        # ルートパス→コントローラー名のマップを構築
        path_to_controller: dict[str, str] = {}
        for r in routes:
            key = f"{r.method} {r.path}"
            if r.controller:
                path_to_controller[key] = r.controller
            # メソッドなしでもマッチできるように
            path_to_controller[r.path] = r.controller

        for uc in usecases:
            controllers: set[str] = set()
            for route_str in uc.related_routes:
                ctrl = path_to_controller.get(route_str)
                if not ctrl:
                    # "GET /api/v1/..." → パス部分だけでも探す
                    parts = route_str.split(" ", 1)
                    if len(parts) == 2:
                        ctrl = path_to_controller.get(parts[1])
                if ctrl:
                    controllers.add(ctrl)
            uc.related_controllers = sorted(controllers)

    def _enrich_pages(
        self, usecases: list[Usecase], pages: list[ParsedPage]
    ) -> None:
        """related_routes と pages の api_calls を突き合わせてビューを紐付けする"""
        if not pages:
            return

        for uc in usecases:
            views: set[str] = set()
            uc_paths = set()
            for route_str in uc.related_routes:
                parts = route_str.split(" ", 1)
                path = parts[1] if len(parts) == 2 else parts[0]
                uc_paths.add(path)

            for page in pages:
                # ページの api_calls がユースケースのルートと一致するか
                for api_call in page.api_calls:
                    call_parts = api_call.split(" ", 1)
                    call_path = call_parts[1] if len(call_parts) == 2 else call_parts[0]
                    if call_path in uc_paths:
                        label = page.component_name or page.route_path
                        if page.route_path and page.route_path != label:
                            label = f"{page.component_name} ({page.route_path})"
                        views.add(label)
                        break

            uc.related_views = sorted(views)
