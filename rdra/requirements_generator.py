"""
要件定義からRDRAモデル生成モジュール

要件定義テキスト（自然言語）を入力として、LLM を使用して
RDRA の全モデル要素を抽出・構造化する。

- エンティティ（情報モデル）
- リレーション（エンティティ間の関係）
- アクター（外部環境）
- ユースケース（事前・事後条件付き）
- 操作シナリオ（正常系・エラー系）
- 状態遷移（ステータスを持つエンティティ）
- ビジネスポリシー（制約・ルール）
"""

import json
import re
from dataclasses import dataclass, field

from llm.provider import LLMProvider
from .information_model import Entity, Relationship
from .state_transition import EntityStateMachine, StateTransition
from .business_policy import BusinessPolicy

from analyzer.usecase_extractor import Usecase
from analyzer.scenario_builder import OperationScenario, OperationStep


SYSTEM_PROMPT = """\
あなたはRDRA（Relationship-Driven Requirements Analysis）の専門家です。
要件定義テキストを分析し、RDRAの全モデル要素を抽出・構造化してください。
日本語で出力してください。英語の要件定義が渡された場合でも、出力は日本語にしてください。
"""


@dataclass
class RDRAGenerationResult:
    """要件定義からのRDRAモデル生成結果"""
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    usecases: list[Usecase] = field(default_factory=list)
    scenarios: list[OperationScenario] = field(default_factory=list)
    state_machines: list[EntityStateMachine] = field(default_factory=list)
    policies: list[BusinessPolicy] = field(default_factory=list)


class RequirementsGenerator:
    """
    要件定義テキストからRDRAモデルを生成するクラス。

    Phase 1: エンティティ・リレーション・アクター抽出
    Phase 2: ユースケース抽出
    Phase 3: 操作シナリオ生成
    Phase 4: 状態遷移・ビジネスポリシー抽出
    """

    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider

    def generate(self, requirements_text: str) -> RDRAGenerationResult:
        """
        要件定義テキストからRDRAモデル一式を生成する。

        Args:
            requirements_text: 要件定義テキスト（自然言語、Markdown可）

        Returns:
            RDRAGenerationResult: 生成されたRDRAモデル一式
        """
        result = RDRAGenerationResult()

        result.entities, result.relationships = self._extract_entities(
            requirements_text
        )

        result.usecases = self._extract_usecases(
            requirements_text, result.entities
        )

        result.scenarios = self._extract_scenarios(
            requirements_text, result.usecases
        )

        result.state_machines = self._extract_state_machines(
            requirements_text, result.entities
        )

        result.policies = self._extract_policies(
            requirements_text, result.entities, result.usecases
        )

        return result

    def _extract_entities(
        self, requirements_text: str
    ) -> tuple[list[Entity], list[Relationship]]:
        """Phase 1: エンティティとリレーションを抽出する"""
        user_message = f"""\
## 要件定義
{requirements_text}

---

上記の要件定義から、情報モデル（エンティティとリレーション）を抽出してください。

### 抽出ルール
1. ドメインの主要な概念をエンティティとして抽出する
2. 各エンティティには主要な属性（5〜10個）を特定する
3. エンティティ間の関係を「1-1」「1-N」「N-N」で分類する
4. システム内部用のエンティティ（セッション、ログ等）は除外する

以下のJSON形式のみで返してください（説明文は不要）:
{{
  "entities": [
    {{
      "name": "ユーザー",
      "class_name": "User",
      "table_name": "users",
      "attributes": ["名前", "メールアドレス", "パスワード", "登録日時"],
      "description": "システムを利用するユーザー"
    }}
  ],
  "relationships": [
    {{
      "from_entity": "ユーザー",
      "to_entity": "注文",
      "relation_type": "1-N",
      "label": "注文する",
      "from_class": "User",
      "to_class": "Order"
    }}
  ]
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=8192,
            )
            return self._parse_entities_response(response)
        except Exception:
            return [], []

    def _parse_entities_response(
        self, response: str
    ) -> tuple[list[Entity], list[Relationship]]:
        """エンティティ抽出のLLMレスポンスをパースする"""
        data = _extract_json(response)
        if not data:
            return [], []

        entities: list[Entity] = []
        for item in data.get("entities", []):
            entities.append(Entity(
                name=item.get("name", ""),
                class_name=item.get("class_name", ""),
                table_name=item.get("table_name", ""),
                attributes=item.get("attributes", []),
                description=item.get("description", ""),
            ))

        relationships: list[Relationship] = []
        for item in data.get("relationships", []):
            relationships.append(Relationship(
                from_entity=item.get("from_entity", ""),
                to_entity=item.get("to_entity", ""),
                relation_type=item.get("relation_type", "1-N"),
                label=item.get("label", ""),
            ))

        return entities, relationships

    def _extract_usecases(
        self, requirements_text: str, entities: list[Entity]
    ) -> list[Usecase]:
        """Phase 2: ユースケースを抽出する"""
        entity_names = [e.name for e in entities]

        user_message = f"""\
## 要件定義
{requirements_text}

## 抽出済みエンティティ
{json.dumps(entity_names, ensure_ascii=False)}

---

上記の要件定義から、ユースケースを抽出してください。

### 抽出ルール
1. 各ユースケースにはアクター（利用者の役割）を特定する
2. 事前条件と事後条件を明記する
3. 関連するエンティティを上記リストから選択する
4. カテゴリで分類する（ユーザー管理、商品管理、注文管理 等）
5. 優先度をhigh/medium/lowで設定する
6. IDは UC-001 形式にする

以下のJSON形式のみで返してください（説明文は不要）:
{{
  "usecases": [
    {{
      "id": "UC-001",
      "name": "ユーザー登録",
      "actor": "未登録ユーザー",
      "description": "新規ユーザーがシステムにアカウントを作成する",
      "preconditions": ["ユーザーが未登録であること"],
      "postconditions": ["ユーザーアカウントが作成される", "確認メールが送信される"],
      "related_entities": ["ユーザー"],
      "category": "ユーザー管理",
      "priority": "high"
    }}
  ]
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=8192,
            )
            return self._parse_usecases_response(response)
        except Exception:
            return []

    def _parse_usecases_response(self, response: str) -> list[Usecase]:
        """ユースケース抽出のLLMレスポンスをパースする"""
        data = _extract_json(response)
        if not data:
            return []

        usecases: list[Usecase] = []
        for item in data.get("usecases", []):
            usecases.append(Usecase(
                id=item.get("id", ""),
                name=item.get("name", ""),
                actor=item.get("actor", ""),
                description=item.get("description", ""),
                preconditions=item.get("preconditions", []),
                postconditions=item.get("postconditions", []),
                related_routes=[],
                related_pages=[],
                related_entities=item.get("related_entities", []),
                category=item.get("category", ""),
                priority=item.get("priority", "medium"),
            ))

        return usecases

    def _extract_scenarios(
        self, requirements_text: str, usecases: list[Usecase]
    ) -> list[OperationScenario]:
        """Phase 3: 操作シナリオを抽出する"""
        if not usecases:
            return []

        uc_summaries = [
            {"id": uc.id, "name": uc.name, "actor": uc.actor,
             "description": uc.description}
            for uc in usecases
        ]

        user_message = f"""\
## 要件定義
{requirements_text}

## ユースケース一覧
```json
{json.dumps(uc_summaries, ensure_ascii=False, indent=2)}
```

---

上記の各ユースケースに対して、操作シナリオ（正常系とエラー系）を生成してください。

### 生成ルール
1. 各ユースケースに最低1つの正常系シナリオを生成する
2. 重要なユースケースにはエラー系シナリオも生成する
3. 各シナリオは3〜8ステップで構成する
4. ステップのアクターは「ユーザー」または「システム」
5. シナリオIDは SC-XXX-01 形式（XXX はユースケース番号）

以下のJSON形式のみで返してください（説明文は不要）:
{{
  "scenarios": [
    {{
      "usecase_id": "UC-001",
      "usecase_name": "ユーザー登録",
      "scenario_id": "SC-001-01",
      "scenario_name": "正常系: メールアドレスで新規登録",
      "scenario_type": "normal",
      "steps": [
        {{
          "step_no": 1,
          "actor": "ユーザー",
          "action": "登録画面を開く",
          "expected_result": "登録フォームが表示される"
        }},
        {{
          "step_no": 2,
          "actor": "ユーザー",
          "action": "必要事項を入力して送信する",
          "expected_result": "入力内容が検証される"
        }},
        {{
          "step_no": 3,
          "actor": "システム",
          "action": "アカウントを作成し確認メールを送信する",
          "expected_result": "登録完了画面が表示される"
        }}
      ],
      "variations": ["SNSアカウントでの登録"]
    }}
  ]
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=16384,
            )
            return self._parse_scenarios_response(response)
        except Exception:
            return []

    def _parse_scenarios_response(
        self, response: str
    ) -> list[OperationScenario]:
        """シナリオ抽出のLLMレスポンスをパースする"""
        data = _extract_json(response)
        if not data:
            return []

        scenarios: list[OperationScenario] = []
        for item in data.get("scenarios", []):
            steps = []
            for step_item in item.get("steps", []):
                steps.append(OperationStep(
                    step_no=step_item.get("step_no", 0),
                    actor=step_item.get("actor", ""),
                    action=step_item.get("action", ""),
                    expected_result=step_item.get("expected_result", ""),
                ))

            scenarios.append(OperationScenario(
                usecase_id=item.get("usecase_id", ""),
                usecase_name=item.get("usecase_name", ""),
                scenario_id=item.get("scenario_id", ""),
                scenario_name=item.get("scenario_name", ""),
                scenario_type=item.get("scenario_type", "normal"),
                steps=steps,
                variations=item.get("variations", []),
            ))

        return scenarios

    def _extract_state_machines(
        self, requirements_text: str, entities: list[Entity]
    ) -> list[EntityStateMachine]:
        """Phase 4a: 状態遷移を抽出する"""
        if not entities:
            return []

        entity_info = [
            {"name": e.name, "class_name": e.class_name,
             "attributes": e.attributes}
            for e in entities
        ]

        user_message = f"""\
## 要件定義
{requirements_text}

## エンティティ一覧
```json
{json.dumps(entity_info, ensure_ascii=False, indent=2)}
```

---

上記の要件定義とエンティティから、状態（ステータス）を持つエンティティを特定し、
状態遷移を定義してください。

### 抽出ルール
1. 明示的にステータスや状態が記述されているエンティティのみ抽出する
2. 状態遷移には、遷移のトリガー（操作やイベント）を明記する
3. 初期状態と最終状態を指定する
4. ガード条件（遷移の前提条件）がある場合は記述する
5. 該当するエンティティがなければ空配列を返す

以下のJSON形式のみで返してください（説明文は不要）:
{{
  "state_machines": [
    {{
      "entity_name": "注文",
      "entity_class": "Order",
      "state_field": "status",
      "states": ["下書き", "確定", "出荷済み", "配達完了", "キャンセル"],
      "transitions": [
        {{
          "from_state": "下書き",
          "to_state": "確定",
          "trigger": "注文確定",
          "guard": "在庫が確保されていること"
        }}
      ],
      "initial_state": "下書き",
      "final_states": ["配達完了", "キャンセル"]
    }}
  ]
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=8192,
            )
            return self._parse_state_machines_response(response)
        except Exception:
            return []

    def _parse_state_machines_response(
        self, response: str
    ) -> list[EntityStateMachine]:
        """状態遷移のLLMレスポンスをパースする"""
        data = _extract_json(response)
        if not data:
            return []

        machines: list[EntityStateMachine] = []
        for item in data.get("state_machines", []):
            transitions = []
            for t in item.get("transitions", []):
                transitions.append(StateTransition(
                    entity_name=item.get("entity_name", ""),
                    from_state=t.get("from_state", ""),
                    to_state=t.get("to_state", ""),
                    trigger=t.get("trigger", ""),
                    guard=t.get("guard", ""),
                ))

            machines.append(EntityStateMachine(
                entity_name=item.get("entity_name", ""),
                entity_class=item.get("entity_class", ""),
                state_field=item.get("state_field", "status"),
                states=item.get("states", []),
                transitions=transitions,
                initial_state=item.get("initial_state", ""),
                final_states=item.get("final_states", []),
            ))

        return machines

    def _extract_policies(
        self,
        requirements_text: str,
        entities: list[Entity],
        usecases: list[Usecase],
    ) -> list[BusinessPolicy]:
        """Phase 4b: ビジネスポリシーを抽出する"""
        entity_names = [e.name for e in entities]
        uc_ids = [uc.id for uc in usecases]

        user_message = f"""\
## 要件定義
{requirements_text}

## 抽出済みエンティティ
{json.dumps(entity_names, ensure_ascii=False)}

## 抽出済みユースケースID
{json.dumps(uc_ids, ensure_ascii=False)}

---

上記の要件定義から、ビジネスポリシー（ビジネスルール・制約・バリデーション）を抽出してください。

### 抽出ルール
1. バリデーションルール（入力制約、形式チェック）
2. 認可ルール（アクセス制御、権限）
3. 計算ルール（料金計算、集計ロジック）
4. 制約（一意性制約、排他制御）
5. ワークフロー（承認フロー、段階的処理）
6. IDは BP-001 形式にする
7. 重要度をmust/should/mayで設定する

以下のJSON形式のみで返してください（説明文は不要）:
{{
  "policies": [
    {{
      "id": "BP-001",
      "name": "メールアドレスの一意性制約",
      "category": "制約",
      "description": "同一メールアドレスでの重複登録を禁止する",
      "related_entities": ["ユーザー"],
      "related_usecases": ["UC-001"],
      "severity": "must"
    }}
  ]
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=8192,
            )
            return self._parse_policies_response(response)
        except Exception:
            return []

    def _parse_policies_response(self, response: str) -> list[BusinessPolicy]:
        """ビジネスポリシーのLLMレスポンスをパースする"""
        data = _extract_json(response)
        if not data:
            return []

        policies: list[BusinessPolicy] = []
        for item in data.get("policies", []):
            policies.append(BusinessPolicy(
                id=item.get("id", ""),
                name=item.get("name", ""),
                category=item.get("category", ""),
                description=item.get("description", ""),
                related_entities=item.get("related_entities", []),
                related_usecases=item.get("related_usecases", []),
                severity=item.get("severity", "must"),
            ))

        return policies


def _extract_json(text: str) -> dict | None:
    """LLMレスポンスからJSON部分を抽出する"""
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not json_match:
        return None

    try:
        return json.loads(json_match.group(0))
    except json.JSONDecodeError:
        return None
