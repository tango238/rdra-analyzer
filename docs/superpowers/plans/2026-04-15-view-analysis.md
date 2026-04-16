# View Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `ScreenSpec`/`UIElement` model and `screen_specs.json` output with teamkit-compatible `ViewScreen` model and `ui.yml` output.

**Architecture:** New `view_model.py` defines dataclasses matching teamkit's `ui.yml` schema. `screen_analyzer.py` keeps its batch processing structure but swaps models, LLM prompts, and output format. Downstream consumers (`scenario_builder`, `scenario_verifier`, `usecase_extractor`, `mermaid_renderer`, `viewer_template`) update references. No new dependencies (PyYAML is already available via standard library-compatible `yaml` or we use a lightweight serializer).

**Tech Stack:** Python dataclasses, PyYAML (for YAML output), existing LLM provider

---

### Task 1: Check PyYAML availability

**Files:**
- Check: `requirements.txt` or `pyproject.toml`

- [ ] **Step 1: Check if PyYAML is installed**

Run: `cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && pip show pyyaml`

If not installed:

Run: `pip install pyyaml && pip freeze | grep -i yaml`

Add `PyYAML` to the project's dependency file if one exists.

- [ ] **Step 2: Commit if dependency added**

```bash
git add requirements.txt  # or pyproject.toml
git commit -m "chore: add PyYAML dependency for ui.yml output"
```

---

### Task 2: Create `view_model.py` with dataclasses

**Files:**
- Create: `analyzer/view_model.py`

- [ ] **Step 1: Create the data model file**

```python
"""
View model definitions for ui.yml schema.

teamkit の ui.yml スキーマに対応するデータクラス。
ソースコード解析で画面の構造（セクション、フィールド、アクション）を表現する。
"""

from dataclasses import dataclass, field


@dataclass
class ViewField:
    """画面内のフィールド（入力項目・表示項目）"""
    id: str                         # snake_case フィールドID
    type: str                       # text, select, data_table, date_picker, number, textarea, etc.
    label: str                      # 日本語ラベル
    required: bool = False
    readonly: bool = False
    placeholder: str = ""
    options: list[dict] = field(default_factory=list)    # [{value, label}]
    columns: list[dict] = field(default_factory=list)    # data_table 用
    extra: dict = field(default_factory=dict)             # type 固有プロパティ (rows, min, max, unit, etc.)


@dataclass
class ViewSection:
    """画面内の論理セクション"""
    section_name: str               # 日本語セクション名
    input_fields: list[ViewField] = field(default_factory=list)


@dataclass
class ViewAction:
    """画面レベルのアクション（ボタン）"""
    id: str
    type: str                       # submit, custom, reset
    label: str                      # 日本語ラベル
    style: str = "primary"          # primary, secondary, danger, link
    confirm: dict | None = None     # {title, message}


@dataclass
class ViewScreen:
    """画面定義（ui.yml の 1 画面に対応）"""
    screen_id: str                  # snake_case 画面ID
    title: str
    description: str = ""
    actor: str = ""
    purpose: str = ""
    sections: list[ViewSection] = field(default_factory=list)
    actions: list[ViewAction] = field(default_factory=list)
    related_models: list[str] = field(default_factory=list)
    related_usecases: list[str] = field(default_factory=list)
```

- [ ] **Step 2: Verify the file is importable**

Run: `cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "from analyzer.view_model import ViewScreen, ViewSection, ViewField, ViewAction; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add analyzer/view_model.py
git commit -m "feat: add view_model.py with ui.yml schema dataclasses"
```

---

### Task 3: Add YAML serialization/deserialization to `view_model.py`

**Files:**
- Modify: `analyzer/view_model.py`

- [ ] **Step 1: Add `save_to_yaml` function**

Append to `analyzer/view_model.py`:

```python
import yaml
from pathlib import Path


def _viewscreen_to_dict(screen: ViewScreen) -> dict:
    """ViewScreen を ui.yml の 1 画面分の dict に変換する"""
    d = {
        "title": screen.title,
        "description": screen.description,
        "actor": screen.actor,
        "purpose": screen.purpose,
    }
    if screen.sections:
        d["sections"] = []
        for sec in screen.sections:
            sec_d = {"section_name": sec.section_name}
            if sec.input_fields:
                sec_d["input_fields"] = []
                for f in sec.input_fields:
                    f_d = {"id": f.id, "type": f.type, "label": f.label}
                    if f.required:
                        f_d["required"] = True
                    if f.readonly:
                        f_d["readonly"] = True
                    if f.placeholder:
                        f_d["placeholder"] = f.placeholder
                    if f.options:
                        f_d["options"] = f.options
                    if f.columns:
                        f_d["columns"] = f.columns
                    if f.extra:
                        f_d.update(f.extra)
                    sec_d["input_fields"].append(f_d)
            d["sections"].append(sec_d)
    if screen.actions:
        d["actions"] = []
        for a in screen.actions:
            a_d = {"id": a.id, "type": a.type, "label": a.label, "style": a.style}
            if a.confirm:
                a_d["confirm"] = a.confirm
            d["actions"].append(a_d)
    if screen.related_models:
        d["related_models"] = screen.related_models
    if screen.related_usecases:
        d["related_usecases"] = screen.related_usecases
    return d


def save_views_to_yaml(screens: list[ViewScreen], output_path: Path) -> None:
    """ViewScreen リストを ui.yml 形式で保存する"""
    view = {}
    for s in screens:
        view[s.screen_id] = _viewscreen_to_dict(s)
    data = {"view": view}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _parse_field(f_dict: dict) -> ViewField:
    """dict から ViewField を復元する"""
    known_keys = {"id", "type", "label", "required", "readonly", "placeholder", "options", "columns"}
    extra = {k: v for k, v in f_dict.items() if k not in known_keys}
    return ViewField(
        id=f_dict.get("id", ""),
        type=f_dict.get("type", ""),
        label=f_dict.get("label", ""),
        required=f_dict.get("required", False),
        readonly=f_dict.get("readonly", False),
        placeholder=f_dict.get("placeholder", ""),
        options=f_dict.get("options", []),
        columns=f_dict.get("columns", []),
        extra=extra,
    )


def load_views_from_yaml(input_path: Path) -> list[ViewScreen]:
    """ui.yml から ViewScreen リストを読み込む"""
    data = yaml.safe_load(input_path.read_text(encoding="utf-8"))
    if not data or "view" not in data:
        return []
    screens = []
    for screen_id, s_dict in data["view"].items():
        sections = []
        for sec in s_dict.get("sections", []):
            fields = [_parse_field(f) for f in sec.get("input_fields", [])]
            sections.append(ViewSection(section_name=sec.get("section_name", ""), input_fields=fields))
        actions = []
        for a in s_dict.get("actions", []):
            actions.append(ViewAction(
                id=a.get("id", ""),
                type=a.get("type", ""),
                label=a.get("label", ""),
                style=a.get("style", "primary"),
                confirm=a.get("confirm"),
            ))
        screens.append(ViewScreen(
            screen_id=screen_id,
            title=s_dict.get("title", ""),
            description=s_dict.get("description", ""),
            actor=s_dict.get("actor", ""),
            purpose=s_dict.get("purpose", ""),
            sections=sections,
            actions=actions,
            related_models=s_dict.get("related_models", []),
            related_usecases=s_dict.get("related_usecases", []),
        ))
    return screens
```

- [ ] **Step 2: Verify round-trip works**

Run:
```bash
cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "
from pathlib import Path
from analyzer.view_model import *
s = ViewScreen(
    screen_id='hotel_list', title='ホテル一覧', description='一覧表示',
    actor='管理者', purpose='ホテル管理',
    sections=[ViewSection(section_name='検索', input_fields=[
        ViewField(id='keyword', type='text', label='キーワード', placeholder='検索')
    ])],
    actions=[ViewAction(id='create', type='submit', label='新規作成', style='primary')],
    related_models=['ホテル'], related_usecases=['ホテル一覧の表示'],
)
p = Path('/tmp/test_ui.yml')
save_views_to_yaml([s], p)
loaded = load_views_from_yaml(p)
assert len(loaded) == 1
assert loaded[0].screen_id == 'hotel_list'
assert loaded[0].sections[0].input_fields[0].label == 'キーワード'
assert loaded[0].actions[0].label == '新規作成'
print('Round-trip OK')
print(p.read_text())
"
```

Expected: `Round-trip OK` followed by valid YAML output.

- [ ] **Step 3: Commit**

```bash
git add analyzer/view_model.py
git commit -m "feat: add YAML save/load for ViewScreen (ui.yml format)"
```

---

### Task 4: Rewrite `screen_analyzer.py` — model and prompt replacement

**Files:**
- Modify: `analyzer/screen_analyzer.py`

This is the largest task. Replace `ScreenSpec`/`UIElement` with `ViewScreen` model, rewrite LLM prompts to request ui.yml schema output, and remove navigation graph logic.

- [ ] **Step 1: Replace imports and remove old models**

At the top of `screen_analyzer.py`, replace the `UIElement` and `ScreenSpec` dataclass definitions and import the new models:

```python
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
```

Remove the `UIElement` class (lines 21-27) and `ScreenSpec` class (lines 31-47) entirely.

- [ ] **Step 2: Rewrite `ScreenAnalyzer.analyze_screens` return type and remove nav graph**

```python
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
```

- [ ] **Step 3: Rewrite `_extract_screen_batch` with ui.yml prompt**

```python
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
```

- [ ] **Step 4: Add new JSON parser `_parse_view_screens_json`**

```python
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
```

- [ ] **Step 5: Rewrite `_fallback_screen`**

```python
    def _fallback_screen(self, page: ParsedPage) -> ViewScreen:
        """ParsedPage から最低限の ViewScreen を生成する"""
        fields = [
            ViewField(id=f"field_{i}", type="text", label=f)
            for i, f in enumerate(page.form_fields)
        ]
        section = ViewSection(section_name="フォーム", input_fields=fields) if fields else None
        # screen_id をファイルパスから生成
        screen_id = re.sub(r"[^a-zA-Z0-9]", "_", page.route_path.strip("/")).strip("_") or page.component_name
        return ViewScreen(
            screen_id=screen_id,
            title=page.component_name,
            description="",
            actor="",
            purpose="",
            sections=[section] if section else [],
        )
```

- [ ] **Step 6: Remove `_build_navigation_graph`, keep `_extract_shared_layouts` and `_parse_layouts_json` unchanged**

Delete the `_build_navigation_graph` method entirely (lines 288-304 of original). The `_extract_shared_layouts` and `_parse_layouts_json` methods remain as-is — they return `dict[str, list]` of menu items used as context for the LLM prompt.

- [ ] **Step 7: Remove old `save_to_json`, `load_from_json` and add thin wrappers**

Delete the `save_to_json` and `load_from_json` static methods. Add wrappers that delegate to `view_model`:

```python
    @staticmethod
    def save_to_yaml(screens: list[ViewScreen], output_path: Path) -> None:
        """画面仕様を ui.yml に保存する"""
        save_views_to_yaml(screens, output_path)

    @staticmethod
    def load_from_yaml(input_path: Path) -> list[ViewScreen]:
        """ui.yml から画面仕様を読み込む"""
        return load_views_from_yaml(input_path)
```

- [ ] **Step 8: Verify the module imports cleanly**

Run: `cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "from analyzer.screen_analyzer import ScreenAnalyzer; print('OK')"`

Expected: `OK`

- [ ] **Step 9: Commit**

```bash
git add analyzer/screen_analyzer.py
git commit -m "feat: rewrite screen_analyzer to ui.yml schema with ViewScreen model"
```

---

### Task 5: Update `scenario_verifier.py`

**Files:**
- Modify: `analyzer/scenario_verifier.py`

The verifier uses `ScreenSpec.action_buttons`, `ScreenSpec.form_fields`, `ScreenSpec.shared_nav_items`, `ScreenSpec.modals`, `ScreenSpec.tabs`, `ScreenSpec.api_actions`, `ScreenSpec.route_path`, `ScreenSpec.page_title`, `ScreenSpec.component_name`. These must map to `ViewScreen` equivalents.

- [ ] **Step 1: Update imports**

Replace line 16:
```python
from .screen_analyzer import ScreenSpec, UIElement
```
with:
```python
from .view_model import ViewScreen, ViewSection, ViewField, ViewAction
```

- [ ] **Step 2: Update type annotations**

Replace all `ScreenSpec` type annotations with `ViewScreen` throughout the file:
- `verify_all(... screen_specs: list[ScreenSpec] ...)` → `verify_all(... screen_specs: list[ViewScreen] ...)`
- `fix_scenarios(... screen_specs: list[ScreenSpec] ...)` → `fix_scenarios(... screen_specs: list[ViewScreen] ...)`
- `_build_api_index(... screen_specs: list[ScreenSpec])` → `_build_api_index(... screen_specs: list[ViewScreen])`
- `_find_matching_screens(... screen_by_route: dict[str, ScreenSpec] ...)` → `_find_matching_screens(... screen_by_route: dict[str, ViewScreen] ...)`
- `_verify_scenario(... screen_by_route: dict[str, ScreenSpec] ...)` → `_verify_scenario(... screen_by_route: dict[str, ViewScreen] ...)`
- `_verify_step(... screens: list[ScreenSpec])` → `_verify_step(... screens: list[ViewScreen])`

- [ ] **Step 3: Update `verify_all` — screen index keying**

The current code uses `s.route_path` as the key. `ViewScreen` doesn't have `route_path` — it has `screen_id`. Update the index to use `screen_id`:

```python
    def verify_all(
        self,
        scenarios: list[OperationScenario],
        screen_specs: list[ViewScreen],
        usecases: list[Usecase],
    ) -> list[VerificationResult]:
        """全シナリオを検証する"""
        screen_by_id = {s.screen_id: s for s in screen_specs}
        results = []
        for sc in scenarios:
            result = self._verify_scenario(sc, screen_by_id, usecases)
            results.append(result)
        return results
```

- [ ] **Step 4: Update `_build_api_index` — extract actions instead of buttons**

The old code iterated `spec.api_actions` and `spec.action_buttons`. With `ViewScreen`, actions don't carry API info. Remove the API-based index entirely since `ViewAction` has no `api_call` field. The verifier will match screens by related_usecases and related_models instead:

```python
    def _build_usecase_index(self, screen_specs: list[ViewScreen]) -> dict[str, list[ViewScreen]]:
        """ユースケース名 → 画面のインデックス"""
        index: dict[str, list[ViewScreen]] = {}
        for spec in screen_specs:
            for uc_name in spec.related_usecases:
                index.setdefault(uc_name, []).append(spec)
        return index
```

- [ ] **Step 5: Rewrite `_find_matching_screens`**

Match by `related_usecases` overlap instead of URL/API matching:

```python
    def _find_matching_screens(
        self,
        scenario: OperationScenario,
        screen_by_id: dict[str, ViewScreen],
        uc_map: dict[str, Usecase],
    ) -> list[ViewScreen]:
        """シナリオに関連する画面を特定する"""
        matched = []
        all_screens = list(screen_by_id.values())

        uc = uc_map.get(scenario.usecase_id)
        if not uc:
            return matched

        # ユースケース名で直接マッチ
        for screen in all_screens:
            for uc_name in screen.related_usecases:
                if uc.name in uc_name or uc_name in uc.name:
                    if screen not in matched:
                        matched.append(screen)

        # related_entities でマッチ
        if not matched:
            for screen in all_screens:
                for model in screen.related_models:
                    for entity in uc.related_entities:
                        if model == entity or model in entity or entity in model:
                            if screen not in matched:
                                matched.append(screen)

        return matched
```

- [ ] **Step 6: Rewrite `_verify_scenario` — extract labels from sections**

```python
    def _verify_scenario(
        self,
        scenario: OperationScenario,
        screen_by_id: dict[str, ViewScreen],
        uc_map: dict[str, Usecase],
    ) -> VerificationResult:
        """単一シナリオを検証する"""
        matched_screens = self._find_matching_screens(scenario, screen_by_id, uc_map)
        issues = []
        verified = 0

        if not matched_screens:
            issues.append(VerificationIssue(
                scenario_id=scenario.scenario_id,
                step_no=0,
                issue_type="no_matching_screen",
                description="対応する画面仕様が見つかりません",
                action_text="",
            ))
            return VerificationResult(
                scenario_id=scenario.scenario_id,
                usecase_id=scenario.usecase_id,
                total_steps=len(scenario.steps),
                verified_steps=0,
                issues=issues,
            )

        # 全画面の UI ラベルを集約
        all_labels = set()
        button_labels = set()
        field_labels = set()
        for screen in matched_screens:
            for action in screen.actions:
                button_labels.add(action.label)
                all_labels.add(action.label)
            for section in screen.sections:
                for f in section.input_fields:
                    field_labels.add(f.label)
                    all_labels.add(f.label)

        for step in scenario.steps:
            if step.actor == "システム":
                verified += 1
                continue
            step_issues = self._verify_step(
                step, scenario.scenario_id,
                all_labels, button_labels, field_labels, set(),
                matched_screens,
            )
            if step_issues:
                issues.extend(step_issues)
            else:
                verified += 1

        return VerificationResult(
            scenario_id=scenario.scenario_id,
            usecase_id=scenario.usecase_id,
            total_steps=len(scenario.steps),
            verified_steps=verified,
            issues=issues,
        )
```

- [ ] **Step 7: Update `fix_scenarios` method**

Replace `screen_by_route` with `screen_by_id`, remove `_build_api_index` calls, update `all_nav_labels` extraction (no more `shared_nav_items`):

```python
    def fix_scenarios(
        self,
        scenarios: list[OperationScenario],
        screen_specs: list[ViewScreen],
        usecases: list[Usecase],
        results: list[VerificationResult],
        already_fixed: set[str] = None,
    ) -> list[OperationScenario]:
        """検証結果をもとにLLMでシナリオを修正する"""
        if not self._llm:
            return scenarios

        already_fixed = already_fixed or set()
        screen_by_id = {s.screen_id: s for s in screen_specs}
        uc_map = {uc.id: uc for uc in usecases}

        targets = [(sc, next((r for r in results if r.scenario_id == sc.scenario_id), None))
                   for sc in scenarios]
        to_fix = sum(1 for _, r in targets if r and r.issues and _.scenario_id not in already_fixed)

        import sys
        if already_fixed:
            print(f"  前回修正済み: {len(already_fixed)}件をスキップ", file=sys.stderr, flush=True)

        fixed = []
        fix_count = 0
        for sc, result in targets:
            if result and result.issues and sc.scenario_id not in already_fixed:
                fix_count += 1
                print(f"  [{fix_count}/{to_fix}] {sc.scenario_id} ({len(result.issues)}件の問題)...", file=sys.stderr, flush=True)
                fixed_sc = self._fix_scenario_with_llm(sc, result, screen_by_id, uc_map)
                fixed.append(fixed_sc)
            else:
                fixed.append(sc)

            if self._save_callback and fix_count > 0 and fix_count % 10 == 0:
                self._save_callback(fixed, scenarios[len(fixed):])

        return fixed
```

- [ ] **Step 8: Rewrite `_fix_scenario_with_llm` screen context builder**

```python
    def _fix_scenario_with_llm(
        self,
        scenario: OperationScenario,
        result: VerificationResult,
        screen_by_id: dict[str, ViewScreen],
        uc_map: dict[str, Usecase],
    ) -> OperationScenario:
        """LLMでシナリオを修正する"""
        matched_screens = self._find_matching_screens(scenario, screen_by_id, uc_map)

        screen_context = ""
        for screen in matched_screens:
            screen_context += f"\n画面: {screen.screen_id} ({screen.title})\n"
            for section in screen.sections:
                screen_context += f"  セクション: {section.section_name}\n"
                for f in section.input_fields:
                    screen_context += f"    - {f.label} ({f.type})\n"
            if screen.actions:
                screen_context += f"  アクション: {', '.join(a.label for a in screen.actions)}\n"

        issues_text = "\n".join([
            f"  Step {i.step_no}: {i.description} (アクション: {i.action_text}){' → ' + i.suggestion if i.suggestion else ''}"
            for i in result.issues
        ])

        steps_text = "\n".join([
            f"  Step {s.step_no}: [{s.actor}] {s.action} → {s.expected_result}"
            for s in scenario.steps
        ])

        system_prompt = """あなたはRDRA専門家です。操作シナリオを実際の画面仕様に基づいて修正してください。

重要: 画面仕様に存在しないUI要素（ボタン、メニュー、フォーム項目）は使用しないでください。
実際に存在するUI要素のみを使ってステップを書き直してください。

以下のJSON形式で回答してください:
{
  "steps": [
    {
      "step_no": 1,
      "actor": "ユーザー|システム",
      "action": "修正後のアクション",
      "expected_result": "期待結果",
      "ui_element": "UI要素名"
    }
  ]
}"""

        user_message = f"""
## シナリオ
- ID: {scenario.scenario_id}
- ユースケース: {scenario.usecase_id} {scenario.usecase_name}
- 種別: {scenario.scenario_type}

## 現在のステップ
{steps_text}

## 検証で見つかった問題
{issues_text}

## 実際の画面仕様
{screen_context}

上記の画面仕様に基づいて、問題のあるステップを修正してください。
画面に存在するUI要素のみを使用してください。
"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=system_prompt,
            )
            return self._parse_fixed_scenario(response, scenario)
        except Exception:
            return scenario
```

- [ ] **Step 9: Remove `_normalize_api_path` and `_extract_resource_name` static methods**

These are no longer needed since we don't match by API paths.

- [ ] **Step 10: Verify the module imports cleanly**

Run: `cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "from analyzer.scenario_verifier import ScenarioVerifier; print('OK')"`

Expected: `OK`

- [ ] **Step 11: Commit**

```bash
git add analyzer/scenario_verifier.py
git commit -m "refactor: update scenario_verifier to use ViewScreen model"
```

---

### Task 6: Update `scenario_builder.py`

**Files:**
- Modify: `analyzer/scenario_builder.py`

The builder accesses `screen.action_buttons`, `screen.form_fields`, `screen.shared_nav_items`, `screen.modals`, `screen.tabs`, `screen.api_actions`, `screen.route_path`, `screen.page_title`, `screen.component_name`.

- [ ] **Step 1: Update `_build_screen_api_index` to use `related_models`**

The old code matched by API resource names. Since `ViewScreen` has no API info, match by `related_models` and `related_usecases`:

```python
    def _build_screen_model_index(self) -> dict:
        """画面仕様のモデル名インデックスを構築"""
        index = {}
        for spec in self._screen_specs:
            for model in spec.related_models:
                index.setdefault(model, []).append(spec)
        return index
```

Rename `self._screen_api_index` to `self._screen_model_index` and update `__init__`:

```python
    def __init__(self, llm_provider: LLMProvider, screen_specs: list = None):
        self._llm = llm_provider
        self._screen_specs = screen_specs or []
        self._screen_model_index = self._build_screen_model_index()
```

- [ ] **Step 2: Rewrite `_find_screens_for_usecase`**

```python
    def _find_screens_for_usecase(self, usecase: Usecase) -> list:
        """ユースケースに関連する画面仕様を特定する"""
        matched = []
        # related_entities でマッチ
        for entity in usecase.related_entities:
            for spec in self._screen_model_index.get(entity, []):
                if spec not in matched:
                    matched.append(spec)
        # related_usecases でマッチ
        if not matched:
            for spec in self._screen_specs:
                for uc_name in spec.related_usecases:
                    if usecase.name in uc_name or uc_name in usecase.name:
                        if spec not in matched:
                            matched.append(spec)
        return matched
```

- [ ] **Step 3: Rewrite `_build_screen_context`**

```python
    def _build_screen_context(self, screens: list) -> str:
        """画面仕様をLLMプロンプト用テキストに変換する"""
        if not screens:
            return ""

        lines = ["\n## 実際の画面仕様（この情報に基づいてステップを生成してください）"]
        for screen in screens[:5]:
            lines.append(f"\n### 画面: {screen.screen_id} ({screen.title})")
            for section in screen.sections:
                lines.append(f"  セクション: {section.section_name}")
                for f in section.input_fields:
                    label = f.label
                    if f.type == "data_table":
                        col_labels = [c.get("label", "") for c in f.columns[:5]]
                        label += f" [列: {', '.join(col_labels)}]"
                    lines.append(f"    - {label} ({f.type})")
            if screen.actions:
                lines.append(f"  アクション: {', '.join(a.label for a in screen.actions)}")

        return "\n".join(lines)
```

- [ ] **Step 4: Update `build_and_validate_for_usecase` label extraction**

Replace lines 100-118 (the label extraction block):

```python
        # 画面のUI要素を集約
        all_labels = set()
        button_labels = set()
        field_labels = set()
        menu_labels = set()
        for screen in matched_screens:
            for a in screen.actions:
                button_labels.add(a.label)
                all_labels.add(a.label)
            for section in screen.sections:
                for f in section.input_fields:
                    field_labels.add(f.label)
                    all_labels.add(f.label)
```

- [ ] **Step 5: Update `_build_for_usecase` — remove `api_only` logic referencing old fields**

The `api_only` check at line 292 references `has_screens` and `self._screen_specs`. Update to work with `ViewScreen`:

```python
        has_screens = bool(screen_context)
        api_only = not has_screens and self._screen_specs
```

This logic doesn't reference `ScreenSpec` fields directly, so it works as-is.

- [ ] **Step 6: Verify the module imports cleanly**

Run: `cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "from analyzer.scenario_builder import ScenarioBuilder; print('OK')"`

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add analyzer/scenario_builder.py
git commit -m "refactor: update scenario_builder to use ViewScreen model"
```

---

### Task 7: Update `usecase_extractor.py`

**Files:**
- Modify: `analyzer/usecase_extractor.py` (lines 100, 139-155)

The extractor uses `screen_specs` to build LLM context. It accesses `spec.route_path`, `spec.page_title`, `spec.action_buttons`, `spec.form_fields`, `spec.modals`, `spec.tabs`.

- [ ] **Step 1: Update the `screen_specs` context builder (lines 139-157)**

Replace:
```python
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
```

With:
```python
        if screen_specs:
            screen_lines: list[str] = []
            for spec in screen_specs[:50]:
                line = f"  {spec.screen_id}: {spec.title or '(無題)'}"
                # セクション内のフィールドラベルを集約
                field_labels = []
                for section in spec.sections:
                    for f in section.input_fields[:5]:
                        field_labels.append(f.label)
                if field_labels:
                    line += f" [フィールド: {', '.join(field_labels[:8])}]"
                if spec.actions:
                    action_names = [a.label for a in spec.actions[:5]]
                    line += f" [アクション: {', '.join(action_names)}]"
                screen_lines.append(line)
            parts.append("## 画面仕様（UI要素）")
            parts.append("\n".join(screen_lines))
            parts.append("")
```

- [ ] **Step 2: Verify**

Run: `cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "from analyzer.usecase_extractor import UsecaseExtractor; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add analyzer/usecase_extractor.py
git commit -m "refactor: update usecase_extractor screen context for ViewScreen"
```

---

### Task 8: Update `mermaid_renderer.py` — viewer data serialization

**Files:**
- Modify: `rdra/mermaid_renderer.py` (lines 170, 238-262)

- [ ] **Step 1: Update the `screen_specs` data serialization**

Replace lines 238-262:
```python
            "screen_specs": [
                {"route_path": s.route_path, "file_path": s.file_path,
                 "component_name": s.component_name, "page_title": s.page_title,
                 ...
                for s in (screen_specs or [])
            ],
```

With:
```python
            "screen_specs": [
                {"screen_id": s.screen_id,
                 "title": s.title,
                 "description": s.description,
                 "actor": s.actor,
                 "purpose": s.purpose,
                 "sections": [
                     {"section_name": sec.section_name,
                      "input_fields": [
                          {"id": f.id, "type": f.type, "label": f.label,
                           "required": f.required, "columns": f.columns}
                          for f in sec.input_fields
                      ]}
                     for sec in s.sections
                 ],
                 "actions": [
                     {"id": a.id, "type": a.type, "label": a.label,
                      "style": a.style}
                     for a in s.actions
                 ],
                 "related_models": s.related_models,
                 "related_usecases": s.related_usecases}
                for s in (screen_specs or [])
            ],
```

- [ ] **Step 2: Verify**

Run: `cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "from rdra.mermaid_renderer import RDRARenderer; print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add rdra/mermaid_renderer.py
git commit -m "refactor: update mermaid_renderer screen data for ViewScreen"
```

---

### Task 9: Update `viewer_template.py` — screen list and detail panel

**Files:**
- Modify: `rdra/viewer_template.py` (lines 291-297, 528-534, 1078-1128)

- [ ] **Step 1: Update `getScreenList` (line 530)**

Replace:
```javascript
  SCREEN_LIST = (DATA.screen_specs||[]).map((s,i) => ({{
    id: `SC-${{String(i+1).padStart(3,"0")}}`,
    ...s,
  }}));
```

With:
```javascript
  SCREEN_LIST = (DATA.screen_specs||[]).map((s,i) => ({{
    id: s.screen_id || `SC-${{String(i+1).padStart(3,"0")}}`,
    ...s,
  }}));
```

- [ ] **Step 2: Update `screenTable` (lines 291-298)**

Replace:
```javascript
function screenTable() {{
  const screens = getScreenList();
  if(!screens.length) return `<p style="color:var(--text-muted)">画面データがありません。<code>python main.py analyze</code> を実行してください。</p>`;
  const rows = screens.map(s =>
    `<tr><td>${{s.id}}</td><td class="clickable" data-screen="${{s.route_path}}" style="cursor:pointer;color:var(--accent)">${{s.route_path}}</td><td>${{s.component_name}}</td><td>${{s.page_title||""}}</td><td>${{s.layout_type||""}}</td><td>${{(s.action_buttons||[]).length}}</td><td>${{(s.form_fields||[]).length}}</td></tr>`
  ).join("");
  return sortableTable("screen-tbl",["ID","ルート","コンポーネント","タイトル","レイアウト","ボタン数","フィールド数"],rows);
}}
```

With:
```javascript
function screenTable() {{
  const screens = getScreenList();
  if(!screens.length) return `<p style="color:var(--text-muted)">画面データがありません。<code>python main.py analyze</code> を実行してください。</p>`;
  const rows = screens.map(s => {{
    const sectionCount = (s.sections||[]).length;
    const fieldCount = (s.sections||[]).reduce((sum, sec) => sum + (sec.input_fields||[]).length, 0);
    return `<tr><td class="clickable" data-screen="${{s.screen_id}}" style="cursor:pointer;color:var(--accent)">${{s.screen_id}}</td><td>${{s.title||""}}</td><td>${{s.actor||""}}</td><td>${{sectionCount}}</td><td>${{fieldCount}}</td><td>${{(s.actions||[]).length}}</td></tr>`;
  }}).join("");
  return sortableTable("screen-tbl",["画面ID","タイトル","アクター","セクション数","フィールド数","アクション数"],rows);
}}
```

- [ ] **Step 3: Update `showScreenDetail` (lines 1078-1128)**

Replace the entire function:
```javascript
function showScreenDetail(screenId) {{
  const scr = (DATA.screen_specs||[]).find(s => s.screen_id === screenId);
  if(!scr) return;

  let html = `<div class="detail-title">${{scr.title}}</div>`;
  html += `<div class="detail-section">`;
  if(scr.description) html += `<p>${{scr.description}}</p>`;
  if(scr.actor) html += `<p>アクター: ${{scr.actor}}</p>`;
  if(scr.purpose) html += `<p>目的: ${{scr.purpose}}</p>`;
  html += `</div>`;

  // セクション & フィールド
  (scr.sections||[]).forEach(sec => {{
    html += `<div class="detail-section"><h4>${{sec.section_name}}</h4>`;
    if(sec.input_fields && sec.input_fields.length) {{
      html += `<table class="data-table"><thead><tr><th>ラベル</th><th>種別</th><th>必須</th></tr></thead><tbody>`;
      sec.input_fields.forEach(f => {{
        const req = f.required ? '<span style="color:var(--high)">*</span>' : '';
        let typeLabel = f.type;
        if(f.type === 'data_table' && f.columns) {{
          typeLabel += ` (${{f.columns.length}}列)`;
        }}
        html += `<tr><td>${{f.label}}</td><td>${{typeLabel}}</td><td>${{req}}</td></tr>`;
      }});
      html += `</tbody></table>`;
    }}
    html += `</div>`;
  }});

  // アクション
  if(scr.actions && scr.actions.length) {{
    html += `<div class="detail-section"><h4>アクション</h4>`;
    html += `<table class="data-table"><thead><tr><th>ラベル</th><th>種別</th><th>スタイル</th></tr></thead><tbody>`;
    scr.actions.forEach(a => {{
      html += `<tr><td>${{a.label}}</td><td>${{a.type}}</td><td>${{a.style||""}}</td></tr>`;
    }});
    html += `</tbody></table></div>`;
  }}

  // 関連モデル
  if(scr.related_models && scr.related_models.length) {{
    html += `<div class="detail-section"><h4>関連モデル</h4><ul class="detail-list">${{scr.related_models.map(m => {{
      const entity = (DATA.entities||[]).find(e => e.name === m);
      return entity ? `<li class="clickable" onclick="showEntityDetail('${{m}}')" style="color:var(--accent);cursor:pointer">${{m}}</li>` : `<li>${{m}}</li>`;
    }}).join("")}}</ul></div>`;
  }}

  // 関連ユースケース
  if(scr.related_usecases && scr.related_usecases.length) {{
    html += `<div class="detail-section"><h4>関連ユースケース</h4><ul class="detail-list">${{scr.related_usecases.map(u => {{
      const uc = (DATA.usecases||[]).find(x => x.name === u);
      return uc ? `<li class="clickable" data-uc-condition="${{uc.id}}" style="color:var(--accent);cursor:pointer">${{u}}</li>` : `<li>${{u}}</li>`;
    }}).join("")}}</ul></div>`;
  }}

  openDetail(html, true);
}}
```

- [ ] **Step 4: Update click handler (line 822)**

Find the line with `data-screen` click handler and update it to pass `screen_id` instead of `route_path`:

The current handler at line 822 reads:
```javascript
  if(screen && !screen.closest("#search-results")) {{ showScreenDetail(screen.dataset.screen); return; }}
```

This works as-is since we changed `data-screen` to contain `screen_id` in Step 2.

- [ ] **Step 5: Verify the file has no syntax errors**

Run: `cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "from rdra.viewer_template import generate_viewer_html; print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add rdra/viewer_template.py
git commit -m "refactor: update viewer screen tab for ui.yml schema"
```

---

### Task 10: Update `main.py` — file paths and imports

**Files:**
- Modify: `main.py`

All references to `screen_specs.json` must change to `ui.yml`, and `ScreenAnalyzer.load_from_json`/`save_to_json` calls must change to `load_from_yaml`/`save_to_yaml`.

- [ ] **Step 1: Update the `analyze` command section**

Find and replace all occurrences:

| Old | New |
|-----|-----|
| `"screen_specs.json"` | `"ui.yml"` |
| `ScreenAnalyzer.load_from_json(screen_path)` | `ScreenAnalyzer.load_from_yaml(screen_path)` |
| `ScreenAnalyzer.save_to_json(screen_specs, screen_path)` | `ScreenAnalyzer.save_to_yaml(screen_specs, screen_path)` |
| `screen_analyzer._build_navigation_graph(screen_specs)` | (delete this line) |
| The 4-line block injecting shared nav items | (delete this block) |

These appear at approximately lines 322, 327, 381-382, 385-391, 391-392, 527-530, 627-633, 828, 1254-1257.

- [ ] **Step 2: Remove shared nav injection block**

Find the block (approximately lines 385-392):
```python
            screen_analyzer._build_navigation_graph(screen_specs)
            for spec in screen_specs:
                ...shared_layouts...
```
Delete these lines entirely.

- [ ] **Step 3: Update the `screens` subcommand (around line 751)**

The docstring mentions `screen_specs.json`. Update to `ui.yml`:

```python
    実際のコンポーネントから抽出し ui.yml に保存する。
```

- [ ] **Step 4: Verify**

Run: `cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "from main import app; print('OK')"`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "refactor: update main.py to use ui.yml instead of screen_specs.json"
```

---

### Task 11: End-to-end verification

**Files:**
- All modified files

- [ ] **Step 1: Check all imports resolve**

```bash
cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "
from analyzer.view_model import ViewScreen, ViewSection, ViewField, ViewAction, save_views_to_yaml, load_views_from_yaml
from analyzer.screen_analyzer import ScreenAnalyzer
from analyzer.scenario_builder import ScenarioBuilder
from analyzer.scenario_verifier import ScenarioVerifier
from analyzer.usecase_extractor import UsecaseExtractor
from rdra.mermaid_renderer import RDRARenderer
from rdra.viewer_template import generate_viewer_html
from main import app
print('All imports OK')
"
```

Expected: `All imports OK`

- [ ] **Step 2: Verify YAML round-trip with realistic data**

```bash
cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && python -c "
from pathlib import Path
from analyzer.view_model import *

screens = [
    ViewScreen(
        screen_id='hotel_list', title='ホテル一覧', description='一覧表示',
        actor='管理者', purpose='ホテル管理',
        sections=[
            ViewSection(section_name='検索', input_fields=[
                ViewField(id='keyword', type='text', label='キーワード'),
            ]),
            ViewSection(section_name='一覧', input_fields=[
                ViewField(id='table', type='data_table', label='ホテル一覧',
                    columns=[{'id': 'name', 'label': 'ホテル名', 'sortable': True}]),
            ]),
        ],
        actions=[
            ViewAction(id='create', type='submit', label='新規作成'),
            ViewAction(id='delete', type='submit', label='削除', style='danger',
                confirm={'title': '確認', 'message': '削除しますか？'}),
        ],
        related_models=['ホテル'],
        related_usecases=['ホテル一覧の表示'],
    ),
    ViewScreen(
        screen_id='hotel_form', title='ホテル登録',
        actor='管理者', purpose='ホテル登録',
        sections=[ViewSection(section_name='基本情報', input_fields=[
            ViewField(id='name', type='text', label='ホテル名', required=True),
            ViewField(id='status', type='select', label='ステータス',
                options=[{'value': 'active', 'label': '有効'}, {'value': 'inactive', 'label': '無効'}]),
        ])],
        actions=[ViewAction(id='save', type='submit', label='保存')],
        related_models=['ホテル'],
    ),
]

p = Path('/tmp/test_ui_full.yml')
save_views_to_yaml(screens, p)
loaded = load_views_from_yaml(p)
assert len(loaded) == 2
assert loaded[0].sections[1].input_fields[0].columns[0]['label'] == 'ホテル名'
assert loaded[1].sections[0].input_fields[1].options[0]['value'] == 'active'
assert loaded[0].actions[1].confirm['title'] == '確認'
print('Full round-trip OK')
print(p.read_text())
"
```

Expected: `Full round-trip OK` followed by valid YAML.

- [ ] **Step 3: Check no remaining references to old types**

```bash
cd /Users/go/work/github/rdra-analyzer/.worktrees/analyze-view && grep -rn "UIElement\|ScreenSpec\|screen_specs\.json\|save_to_json\|load_from_json" analyzer/ rdra/ main.py --include="*.py" | grep -v "__pycache__" | grep -v ".pyc"
```

Expected: No output (no remaining references).

- [ ] **Step 4: Commit any remaining fixes**

If Step 3 found leftover references, fix them and commit:

```bash
git add -A
git commit -m "fix: clean up remaining ScreenSpec/UIElement references"
```
