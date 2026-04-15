"""
画面分析モジュール

フロントエンドのページコンポーネントを深く解析し、
ui.yml スキーマ形式で画面の構造（セクション、フィールド、アクション）を抽出する。
"""

import json
import re
from pathlib import Path

from llm.provider import LLMProvider
from .source_parser import ParsedPage
from .project_context import build_context, format_context_for_prompt
from .view_model import (
    ViewScreen, ViewSection, ViewField, ViewAction,
    save_views_to_yaml, load_views_from_yaml,
)


class ScreenAnalyzer:
    """
    フロントエンドの画面を深く解析するクラス。

    1. 共有レイアウト（サイドバー・ヘッダー）を抽出（参考情報）
    2. 個別ページのUI要素を ui.yml スキーマでバッチ抽出
    """

    DEFAULT_BATCH_SIZE = 5

    def __init__(self, llm_provider: LLMProvider, project_context: str = ""):
        self._llm = llm_provider
        self._project_context = project_context

    def analyze_screens(
        self,
        repo_path: Path,
        pages: list[ParsedPage],
        batch_size: int = None,
    ) -> list[ViewScreen]:
        """画面のUI仕様を ui.yml スキーマで抽出する"""
        batch_size = batch_size or self.DEFAULT_BATCH_SIZE

        ctx = build_context(repo_path)
        context_text = format_context_for_prompt([ctx])

        # Phase A: 共有レイアウト抽出（参考情報として取得）
        shared_layouts = self._extract_shared_layouts(repo_path, context_text)

        # Phase B: 個別ページをバッチで抽出
        specs: list[ViewScreen] = []
        batches = [pages[i:i+batch_size] for i in range(0, len(pages), batch_size)]

        for batch_idx, batch in enumerate(batches):
            batch_specs = self._extract_screen_batch(
                repo_path, batch, context_text, shared_layouts, batch_idx, len(batches)
            )
            specs.extend(batch_specs)

        return specs

    def _extract_shared_layouts(
        self, repo_path: Path, context_text: str
    ) -> dict[str, list[dict]]:
        """共有レイアウトコンポーネント（サイドバー・ヘッダー）を抽出する"""
        prompt = f"""{context_text}

このリポジトリのフロントエンドで使われている共有レイアウトコンポーネントを探してください。

手順:
1. layout.tsx, _layout.tsx, Layout.tsx などのレイアウトファイルを探す
2. サイドバー、ヘッダーナビゲーションのコンポーネントを読む
3. メニュー項目（リンクテキストと遷移先）を抽出する

以下のJSON形式のみで返してください:
{{
  "layouts": {{
    "AdminLayout": [
      {{"label": "ダッシュボード", "target": "/admin/dashboard"}},
      {{"label": "ホテル管理", "target": "/admin/hotels"}}
    ],
    "OwnerLayout": [
      {{"label": "施設管理", "target": "/owner/hotels"}}
    ]
  }}
}}"""

        try:
            result_text = self._llm.analyze_codebase(
                path=str(repo_path),
                prompt=prompt,
                timeout=self._llm._analyze_timeout if hasattr(self._llm, '_analyze_timeout') else 600,
            )
            return self._parse_layouts_json(result_text)
        except Exception as e:
            import sys
            print(f"  [warn] レイアウト抽出に失敗: {e}", file=sys.stderr)
            return {}

    def _extract_screen_batch(
        self,
        repo_path: Path,
        pages_batch: list[ParsedPage],
        context_text: str,
        shared_layouts: dict,
        batch_idx: int,
        total_batches: int,
    ) -> list[ViewScreen]:
        """ページのバッチから ViewScreen を ui.yml スキーマで抽出する"""
        pages_info = []
        for p in pages_batch:
            pages_info.append({
                "route_path": p.route_path,
                "file_path": p.file_path,
                "component_name": p.component_name,
                "page_type": p.page_type,
                "api_calls": p.api_calls,
                "form_fields": p.form_fields,
            })

        layout_names = list(shared_layouts.keys())

        prompt = f"""{context_text}

以下のページコンポーネントを実際に読んで、画面の構造を ui.yml スキーマで抽出してください。
バッチ {batch_idx + 1}/{total_batches}

対象ページ:
{json.dumps(pages_info, ensure_ascii=False, indent=2)}

共有レイアウト: {', '.join(layout_names) if layout_names else '不明'}

抽出ルール:
1. screen_id: ルートパスから snake_case で生成（例: /admin/hotels → admin_hotel_list, /admin/hotels/create → admin_hotel_form）
2. title: ページの見出し（h1, タイトル等）を日本語で
3. actor: ページが属するユーザーロール（レイアウトやルートから推定）
4. sections: フォーム入力や表示データを論理的なセクションにグルーピング
5. input_fields:
   - 一覧画面: data_table 型で columns を定義
   - フォーム画面: text, select, textarea, date_picker, number, checkbox 等
   - 検索・フィルター: text, select 等
6. actions: 画面レベルのボタン（保存, 削除, 新規作成など）
   - type: submit, custom, reset のいずれか
   - style: primary, secondary, danger, link のいずれか
7. related_models: 画面が操作するエンティティ名（日本語）
8. related_usecases: 画面が対応するユースケース名（日本語、推定）

フィールドの options は必ず {{value, label}} 形式にしてください。

以下のJSON形式のみで返してください:
{{
  "screens": [
    {{
      "screen_id": "hotel_list",
      "title": "ホテル一覧",
      "description": "登録済みホテルの一覧表示・検索",
      "actor": "管理者",
      "purpose": "ホテル情報の管理",
      "sections": [
        {{
          "section_name": "検索・フィルター",
          "input_fields": [
            {{"id": "search_keyword", "type": "text", "label": "キーワード検索", "placeholder": "ホテル名で検索"}}
          ]
        }},
        {{
          "section_name": "ホテル一覧",
          "input_fields": [
            {{
              "id": "hotel_table",
              "type": "data_table",
              "label": "ホテル一覧",
              "columns": [
                {{"id": "name", "label": "ホテル名", "sortable": true}},
                {{"id": "status", "label": "ステータス"}}
              ]
            }}
          ]
        }}
      ],
      "actions": [
        {{"id": "create_hotel", "type": "submit", "label": "新規作成", "style": "primary"}}
      ],
      "related_models": ["ホテル"],
      "related_usecases": ["ホテル一覧の表示"]
    }}
  ]
}}"""

        try:
            result_text = self._llm.analyze_codebase(
                path=str(repo_path),
                prompt=prompt,
                timeout=self._llm._analyze_timeout if hasattr(self._llm, '_analyze_timeout') else 600,
            )
            return self._parse_view_screens_json(result_text, pages_batch)
        except Exception as e:
            import sys
            print(f"  [warn] 画面抽出バッチ{batch_idx+1}に失敗: {e}", file=sys.stderr)
            return [self._fallback_screen(p) for p in pages_batch]

    def _parse_layouts_json(self, text: str) -> dict[str, list[dict]]:
        """レイアウトJSONをパースする"""
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return {}
        try:
            data = json.loads(json_match.group())
            layouts = {}
            for name, items in data.get("layouts", {}).items():
                layouts[name] = [
                    {"label": item.get("label", ""), "target": item.get("target", "")}
                    for item in items
                ]
            return layouts
        except (json.JSONDecodeError, KeyError):
            return {}

    def _parse_view_screens_json(
        self, text: str, pages_batch: list[ParsedPage]
    ) -> list[ViewScreen]:
        """LLM出力JSONを ViewScreen リストにパースする"""
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return [self._fallback_screen(p) for p in pages_batch]

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return [self._fallback_screen(p) for p in pages_batch]

        screens = []
        for item in data.get("screens", []):
            sections = []
            for sec in item.get("sections", []):
                fields = []
                for f in sec.get("input_fields", []):
                    known_keys = {"id", "type", "label", "required", "readonly", "placeholder", "options", "columns"}
                    extra = {k: v for k, v in f.items() if k not in known_keys}
                    # options の正規化: フラット文字列配列 → {value, label} 形式
                    options = f.get("options", [])
                    if options and isinstance(options[0], str):
                        options = [{"value": o, "label": o} for o in options]
                    fields.append(ViewField(
                        id=f.get("id", ""),
                        type=f.get("type", ""),
                        label=f.get("label", ""),
                        required=f.get("required", False),
                        readonly=f.get("readonly", False),
                        placeholder=f.get("placeholder", ""),
                        options=options,
                        columns=f.get("columns", []),
                        extra=extra,
                    ))
                sections.append(ViewSection(
                    section_name=sec.get("section_name", ""),
                    input_fields=fields,
                ))

            actions = []
            for a in item.get("actions", []):
                actions.append(ViewAction(
                    id=a.get("id", ""),
                    type=a.get("type", "submit"),
                    label=a.get("label", ""),
                    style=a.get("style", "primary"),
                    confirm=a.get("confirm"),
                ))

            screens.append(ViewScreen(
                screen_id=item.get("screen_id", ""),
                title=item.get("title", ""),
                description=item.get("description", ""),
                actor=item.get("actor", ""),
                purpose=item.get("purpose", ""),
                sections=sections,
                actions=actions,
                related_models=item.get("related_models", []),
                related_usecases=item.get("related_usecases", []),
            ))

        return screens

    def _fallback_screen(self, page: ParsedPage) -> ViewScreen:
        """ParsedPage から最低限の ViewScreen を生成する"""
        fields = [
            ViewField(id=f"field_{i}", type="text", label=f)
            for i, f in enumerate(page.form_fields)
        ]
        section = ViewSection(section_name="フォーム", input_fields=fields) if fields else None
        screen_id = re.sub(r"[^a-zA-Z0-9]", "_", page.route_path.strip("/")).strip("_") or page.component_name
        return ViewScreen(
            screen_id=screen_id,
            title=page.component_name,
            sections=[section] if section else [],
        )

    @staticmethod
    def save_to_yaml(screens: list[ViewScreen], output_path: Path) -> None:
        """画面仕様を ui.yml に保存する"""
        save_views_to_yaml(screens, output_path)

    @staticmethod
    def load_from_yaml(input_path: Path) -> list[ViewScreen]:
        """ui.yml から画面仕様を読み込む"""
        return load_views_from_yaml(input_path)
