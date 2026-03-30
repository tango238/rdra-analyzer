"""
画面分析モジュール

フロントエンドのページコンポーネントを深く解析し、
実際のUI要素（ボタン、フォーム、メニュー、モーダル等）を抽出する。

シナリオ生成時に実際のUI構造に基づいたステップを生成するために使用する。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from llm.provider import LLMProvider
from .source_parser import ParsedPage
from .project_context import build_context, format_context_for_prompt


@dataclass
class UIElement:
    """UIの操作可能な要素"""
    element_type: str       # button, link, menu_item, tab, form_field, modal_trigger, select, checkbox, search_input
    label: str              # 表示テキスト: "保存", "検索", "ホテル一覧"
    target: str = ""        # 遷移先やアクション: "/hotels", "openModal('confirm')"
    api_call: str = ""      # トリガーされるAPI: "POST /api/v2/hotels"
    parent_section: str = "" # 所属セクション: "header", "sidebar", "main_form", "modal"


@dataclass
class ScreenSpec:
    """画面ごとのUI仕様"""
    route_path: str                 # URLパス
    file_path: str                  # コンポーネントファイルパス
    component_name: str             # コンポーネント名
    page_title: str = ""            # ページタイトル/見出し
    layout_type: str = ""           # sidebar_layout, tab_layout, simple_form, dashboard
    navigation_items: list[UIElement] = field(default_factory=list)
    action_buttons: list[UIElement] = field(default_factory=list)
    form_fields: list[UIElement] = field(default_factory=list)
    modals: list[str] = field(default_factory=list)
    tabs: list[str] = field(default_factory=list)
    api_actions: dict[str, str] = field(default_factory=dict)  # ボタンラベル → API
    parent_page: str = ""
    child_pages: list[str] = field(default_factory=list)
    shared_layout: str = ""
    shared_nav_items: list[UIElement] = field(default_factory=list)


class ScreenAnalyzer:
    """
    フロントエンドの画面を深く解析するクラス。

    1. 共有レイアウト（サイドバー・ヘッダー）を抽出
    2. 個別ページのUI要素をバッチで抽出
    3. 画面間のナビゲーショングラフを構築
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
    ) -> list[ScreenSpec]:
        """画面のUI仕様を抽出する"""
        batch_size = batch_size or self.DEFAULT_BATCH_SIZE

        ctx = build_context(repo_path)
        context_text = format_context_for_prompt([ctx])

        # Phase A: 共有レイアウト抽出
        shared_layouts = self._extract_shared_layouts(repo_path, context_text)

        # Phase B: 個別ページをバッチで抽出
        specs: list[ScreenSpec] = []
        batches = [pages[i:i+batch_size] for i in range(0, len(pages), batch_size)]

        for batch_idx, batch in enumerate(batches):
            batch_specs = self._extract_screen_batch(
                repo_path, batch, context_text, shared_layouts, batch_idx, len(batches)
            )
            specs.extend(batch_specs)

        # ナビゲーショングラフ構築
        self._build_navigation_graph(specs)

        # 共有レイアウトのナビを各画面に注入
        for spec in specs:
            if spec.shared_layout and spec.shared_layout in shared_layouts:
                spec.shared_nav_items = shared_layouts[spec.shared_layout]

        return specs

    def _extract_shared_layouts(
        self, repo_path: Path, context_text: str
    ) -> dict[str, list[UIElement]]:
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
      {{"element_type": "menu_item", "label": "ダッシュボード", "target": "/admin/dashboard"}},
      {{"element_type": "menu_item", "label": "ホテル管理", "target": "/admin/hotels"}}
    ],
    "OwnerLayout": [
      {{"element_type": "menu_item", "label": "施設管理", "target": "/owner/hotels"}}
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
    ) -> list[ScreenSpec]:
        """ページのバッチからScreenSpecを抽出する"""
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

以下のページコンポーネントを実際に読んで、UI要素を詳細に抽出してください。
バッチ {batch_idx + 1}/{total_batches}

対象ページ:
{json.dumps(pages_info, ensure_ascii=False, indent=2)}

手順:
1. 各ページのコンポーネントファイルを読む
2. インポートしているサブコンポーネント（フォーム、テーブル、モーダル）も確認する
3. 以下を抽出:
   - page_title: ページの見出し（h1, タイトル等）
   - layout_type: sidebar_layout / tab_layout / simple_form / dashboard / list_detail
   - action_buttons: ボタン（ラベル、遷移先、呼び出すAPI）
   - form_fields: フォーム入力（ラベル、入力タイプ）
   - modals: モーダル/ダイアログの名前
   - tabs: タブのラベル一覧
   - api_actions: ボタンラベル→APIエンドポイントの対応
   - shared_layout: 使用しているレイアウト名（{', '.join(layout_names) if layout_names else '不明'}）

以下のJSON形式のみで返してください:
{{
  "screens": [
    {{
      "route_path": "/hotels",
      "file_path": "app/(admin)/hotels/page.tsx",
      "component_name": "HotelListPage",
      "page_title": "ホテル一覧",
      "layout_type": "sidebar_layout",
      "action_buttons": [
        {{"element_type": "button", "label": "新規作成", "target": "/hotels/create", "api_call": ""}},
        {{"element_type": "button", "label": "削除", "target": "", "api_call": "DELETE /api/v2/hotels/{{id}}"}}
      ],
      "form_fields": [
        {{"element_type": "search_input", "label": "キーワード検索", "target": "", "api_call": ""}}
      ],
      "modals": ["削除確認"],
      "tabs": [],
      "api_actions": {{"新規作成": "", "削除": "DELETE /api/v2/hotels/{{id}}"}},
      "shared_layout": "AdminLayout"
    }}
  ]
}}"""

        try:
            result_text = self._llm.analyze_codebase(
                path=str(repo_path),
                prompt=prompt,
                timeout=self._llm._analyze_timeout if hasattr(self._llm, '_analyze_timeout') else 600,
            )
            return self._parse_screen_specs_json(result_text, pages_batch)
        except Exception as e:
            import sys
            print(f"  [warn] 画面抽出バッチ{batch_idx+1}に失敗: {e}", file=sys.stderr)
            # フォールバック: ParsedPage から最低限のScreenSpecを生成
            return [self._fallback_spec(p) for p in pages_batch]

    def _parse_layouts_json(self, text: str) -> dict[str, list[UIElement]]:
        """レイアウトJSONをパースする"""
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return {}
        try:
            data = json.loads(json_match.group())
            layouts = {}
            for name, items in data.get("layouts", {}).items():
                elements = []
                for item in items:
                    elements.append(UIElement(
                        element_type=item.get("element_type", "menu_item"),
                        label=item.get("label", ""),
                        target=item.get("target", ""),
                    ))
                layouts[name] = elements
            return layouts
        except (json.JSONDecodeError, KeyError):
            return {}

    def _parse_screen_specs_json(
        self, text: str, pages_batch: list[ParsedPage]
    ) -> list[ScreenSpec]:
        """画面仕様JSONをパースする"""
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if not json_match:
            return [self._fallback_spec(p) for p in pages_batch]

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return [self._fallback_spec(p) for p in pages_batch]

        specs = []
        for item in data.get("screens", []):
            buttons = [UIElement(**{k: b.get(k, "") for k in ["element_type", "label", "target", "api_call"]})
                       for b in item.get("action_buttons", [])]
            fields = [UIElement(**{k: f.get(k, "") for k in ["element_type", "label", "target", "api_call"]})
                      for f in item.get("form_fields", [])]

            specs.append(ScreenSpec(
                route_path=item.get("route_path", ""),
                file_path=item.get("file_path", ""),
                component_name=item.get("component_name", ""),
                page_title=item.get("page_title", ""),
                layout_type=item.get("layout_type", ""),
                action_buttons=buttons,
                form_fields=fields,
                modals=item.get("modals", []),
                tabs=item.get("tabs", []),
                api_actions=item.get("api_actions", {}),
                shared_layout=item.get("shared_layout", ""),
            ))

        return specs

    def _fallback_spec(self, page: ParsedPage) -> ScreenSpec:
        """ParsedPage から最低限のScreenSpecを生成する"""
        fields = [UIElement(element_type="form_field", label=f) for f in page.form_fields]
        return ScreenSpec(
            route_path=page.route_path,
            file_path=page.file_path,
            component_name=page.component_name,
            page_title=page.component_name,
            layout_type=page.page_type,
            form_fields=fields,
        )

    def _build_navigation_graph(self, specs: list[ScreenSpec]) -> None:
        """画面間の親子関係を構築する"""
        route_set = {s.route_path for s in specs}
        for spec in specs:
            # 親ページ推定: /hotels/[id] → /hotels
            parts = spec.route_path.rstrip("/").rsplit("/", 1)
            if len(parts) == 2 and parts[0]:
                parent = parts[0]
                if parent in route_set:
                    spec.parent_page = parent

            # 子ページ: ボタンの遷移先から
            for btn in spec.action_buttons:
                if btn.target and btn.target.startswith("/") and btn.target in route_set:
                    if btn.target not in spec.child_pages:
                        spec.child_pages.append(btn.target)

    @staticmethod
    def save_to_json(specs: list[ScreenSpec], output_path: Path) -> None:
        """画面仕様をJSONファイルに保存する"""
        data = {
            "metadata": {
                "total_screens": len(specs),
            },
            "screen_specs": [
                {
                    "route_path": s.route_path,
                    "file_path": s.file_path,
                    "component_name": s.component_name,
                    "page_title": s.page_title,
                    "layout_type": s.layout_type,
                    "action_buttons": [
                        {"element_type": b.element_type, "label": b.label,
                         "target": b.target, "api_call": b.api_call}
                        for b in s.action_buttons
                    ],
                    "form_fields": [
                        {"element_type": f.element_type, "label": f.label,
                         "target": f.target, "api_call": f.api_call}
                        for f in s.form_fields
                    ],
                    "modals": s.modals,
                    "tabs": s.tabs,
                    "api_actions": s.api_actions,
                    "parent_page": s.parent_page,
                    "child_pages": s.child_pages,
                    "shared_layout": s.shared_layout,
                    "shared_nav_items": [
                        {"element_type": n.element_type, "label": n.label, "target": n.target}
                        for n in s.shared_nav_items
                    ],
                }
                for s in specs
            ],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load_from_json(input_path: Path) -> list[ScreenSpec]:
        """JSONファイルから画面仕様を読み込む"""
        data = json.loads(input_path.read_text(encoding="utf-8"))
        specs = []
        for item in data.get("screen_specs", []):
            buttons = [UIElement(**{k: b.get(k, "") for k in ["element_type", "label", "target", "api_call"]})
                       for b in item.get("action_buttons", [])]
            fields = [UIElement(**{k: f.get(k, "") for k in ["element_type", "label", "target", "api_call"]})
                      for f in item.get("form_fields", [])]
            nav_items = [UIElement(**{k: n.get(k, "") for k in ["element_type", "label", "target"]})
                         for n in item.get("shared_nav_items", [])]
            specs.append(ScreenSpec(
                route_path=item.get("route_path", ""),
                file_path=item.get("file_path", ""),
                component_name=item.get("component_name", ""),
                page_title=item.get("page_title", ""),
                layout_type=item.get("layout_type", ""),
                action_buttons=buttons,
                form_fields=fields,
                modals=item.get("modals", []),
                tabs=item.get("tabs", []),
                api_actions=item.get("api_actions", {}),
                parent_page=item.get("parent_page", ""),
                child_pages=item.get("child_pages", []),
                shared_layout=item.get("shared_layout", ""),
                shared_nav_items=nav_items,
            ))
        return specs
