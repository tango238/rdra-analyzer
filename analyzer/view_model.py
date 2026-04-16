"""
View model definitions for ui.yml schema.

teamkit の ui.yml スキーマに対応するデータクラス。
ソースコード解析で画面の構造（セクション、フィールド、アクション）を表現する。
"""

import yaml
from dataclasses import dataclass, field
from pathlib import Path


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
    confirm: dict = None             # {title, message}


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


# ── YAML serialization ──────────────────────────────────────────


def _viewscreen_to_dict(screen: ViewScreen) -> dict:
    """ViewScreen を ui.yml の 1 画面分の dict に変換する"""
    d: dict = {
        "title": screen.title,
        "description": screen.description,
        "actor": screen.actor,
        "purpose": screen.purpose,
    }
    if screen.sections:
        d["sections"] = []
        for sec in screen.sections:
            sec_d: dict = {"section_name": sec.section_name}
            if sec.input_fields:
                sec_d["input_fields"] = []
                for f in sec.input_fields:
                    f_d: dict = {"id": f.id, "type": f.type, "label": f.label}
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
            a_d: dict = {"id": a.id, "type": a.type, "label": a.label, "style": a.style}
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
