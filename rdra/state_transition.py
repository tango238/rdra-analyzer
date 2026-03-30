"""
状態遷移図生成モジュール

エンティティの status / state フィールドを解析し、
LLM で状態遷移を推定して Mermaid stateDiagram-v2 として出力する。
"""

import json
import re
from dataclasses import dataclass, field

from llm.provider import LLMProvider
from .information_model import Entity


@dataclass
class StateTransition:
    """状態遷移の定義"""
    entity_name: str
    from_state: str
    to_state: str
    trigger: str          # 遷移トリガー（操作・イベント）
    guard: str = ""       # ガード条件


@dataclass
class EntityStateMachine:
    """エンティティの状態マシン定義"""
    entity_name: str
    entity_class: str
    state_field: str                        # status / state 等のフィールド名
    states: list[str] = field(default_factory=list)
    transitions: list[StateTransition] = field(default_factory=list)
    initial_state: str = ""
    final_states: list[str] = field(default_factory=list)


class StateTransitionGenerator:
    """
    エンティティの状態遷移図を生成するクラス。

    1. エンティティの属性から status/state フィールドを検出
    2. LLM で状態一覧・遷移条件を推定
    3. Mermaid stateDiagram-v2 で出力
    """

    def __init__(self, llm_provider: LLMProvider, project_context: str = ""):
        self._llm = llm_provider
        self._project_context = project_context

    def generate(
        self,
        entities: list[Entity],
        routes: list = None,
        usecases: list = None,
    ) -> list[EntityStateMachine]:
        """状態を持つエンティティを検出し、状態遷移を生成する"""
        candidates = self._find_stateful_entities(entities)
        if not candidates:
            return []

        return self._analyze_with_llm(candidates, entities, routes or [], usecases or [])

    def _find_stateful_entities(self, entities: list[Entity]) -> list[tuple[Entity, str]]:
        """status/state フィールドを持つエンティティを検出"""
        state_patterns = re.compile(
            r"^(status|state|phase|stage|step|condition|progress|workflow_status)$",
            re.IGNORECASE,
        )
        candidates = []
        for entity in entities:
            for attr in entity.attributes:
                field_name = attr.split(":")[0].strip().lower()
                if state_patterns.match(field_name):
                    candidates.append((entity, attr.split(":")[0].strip()))
                    break
        return candidates

    def _analyze_with_llm(
        self,
        candidates: list[tuple[Entity, str]],
        entities: list[Entity],
        routes: list,
        usecases: list,
    ) -> list[EntityStateMachine]:
        """LLM で状態遷移を推定する"""
        entity_info = []
        for entity, state_field in candidates:
            entity_info.append({
                "class_name": entity.class_name,
                "name": entity.name,
                "state_field": state_field,
                "attributes": entity.attributes[:20],
            })

        route_summary = ""
        if routes:
            route_lines = [f"  {r.method} {r.path}" for r in routes[:80]]
            route_summary = "\n".join(route_lines)

        uc_summary = ""
        if usecases:
            uc_lines = [f"  {uc.id}: {uc.name} ({uc.actor})" for uc in usecases[:30]]
            uc_summary = "\n".join(uc_lines)

        system_prompt = """あなたはソフトウェアアーキテクトです。
エンティティの状態遷移を分析し、JSON形式で出力してください。

各エンティティについて以下を推定してください:
- states: 取りうる状態の一覧（日本語名）
- initial_state: 初期状態
- final_states: 終了状態（複数可）
- transitions: 状態遷移の一覧
  - from_state: 遷移元
  - to_state: 遷移先
  - trigger: 遷移トリガー（操作やイベント）
  - guard: ガード条件（任意）

出力はJSON配列で:
```json
[
  {
    "class_name": "Booking",
    "state_field": "status",
    "states": ["仮予約", "確定", "チェックイン", "チェックアウト", "キャンセル"],
    "initial_state": "仮予約",
    "final_states": ["チェックアウト", "キャンセル"],
    "transitions": [
      {"from": "仮予約", "to": "確定", "trigger": "予約確認", "guard": "決済完了"},
      {"from": "確定", "to": "チェックイン", "trigger": "チェックイン処理", "guard": ""},
      {"from": "確定", "to": "キャンセル", "trigger": "キャンセル申請", "guard": "キャンセルポリシー内"}
    ]
  }
]
```"""

        user_msg = f"""以下のエンティティの状態遷移を分析してください。

エンティティ一覧:
{json.dumps(entity_info, ensure_ascii=False, indent=2)}
"""
        if self._project_context:
            user_msg += f"\nプロジェクトコンテキスト:\n{self._project_context[:2000]}\n"
        if route_summary:
            user_msg += f"\nAPIルート:\n{route_summary}\n"
        if uc_summary:
            user_msg += f"\nユースケース:\n{uc_summary}\n"

        response = self._llm.complete_simple(system_prompt, user_msg)
        return self._parse_response(response, candidates)

    def _parse_response(
        self,
        response: str,
        candidates: list[tuple[Entity, str]],
    ) -> list[EntityStateMachine]:
        """LLMレスポンスをパースする"""
        json_match = re.search(r"\[.*\]", response, re.DOTALL)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return []

        entity_map = {e.class_name: (e, sf) for e, sf in candidates}
        machines = []

        for item in data:
            class_name = item.get("class_name", "")
            if class_name not in entity_map:
                continue

            entity, state_field = entity_map[class_name]
            transitions = []
            for t in item.get("transitions", []):
                transitions.append(StateTransition(
                    entity_name=entity.name,
                    from_state=t.get("from", ""),
                    to_state=t.get("to", ""),
                    trigger=t.get("trigger", ""),
                    guard=t.get("guard", ""),
                ))

            machines.append(EntityStateMachine(
                entity_name=entity.name,
                entity_class=class_name,
                state_field=state_field,
                states=item.get("states", []),
                transitions=transitions,
                initial_state=item.get("initial_state", ""),
                final_states=item.get("final_states", []),
            ))

        return machines

    def to_mermaid(self, machine: EntityStateMachine) -> str:
        """単一エンティティの状態遷移を Mermaid stateDiagram-v2 で出力"""
        lines = ["stateDiagram-v2"]

        if machine.initial_state:
            safe_initial = self._safe_id(machine.initial_state)
            lines.append(f"    [*] --> {safe_initial}")

        for state in machine.states:
            safe = self._safe_id(state)
            lines.append(f"    {safe} : {state}")

        for t in machine.transitions:
            safe_from = self._safe_id(t.from_state)
            safe_to = self._safe_id(t.to_state)
            label = t.trigger
            if t.guard:
                label += f" [{t.guard}]"
            lines.append(f"    {safe_from} --> {safe_to} : {label}")

        for fs in machine.final_states:
            safe_fs = self._safe_id(fs)
            lines.append(f"    {safe_fs} --> [*]")

        return "\n".join(lines)

    def to_mermaid_all(self, machines: list[EntityStateMachine]) -> str:
        """全エンティティの状態遷移を結合して出力"""
        sections = []
        for m in machines:
            sections.append(self.to_mermaid(m))
        return "\n\n".join(sections)

    @staticmethod
    def _safe_id(text: str) -> str:
        """Mermaid で安全に使えるID文字列を生成"""
        safe = re.sub(r"[^\w]", "_", text)
        if not safe or safe[0].isdigit():
            safe = "S_" + safe
        return safe
