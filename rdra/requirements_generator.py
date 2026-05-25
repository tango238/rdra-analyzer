"""
要件定義からRDRAモデル生成モジュール

RDRA2.0 の4層レイヤー構造に沿い、要件定義テキストから段階的にモデルを抽出する。

Layer 1 - システム価値:   アクター・外部システム・要求
Layer 2 - システム外部環境: ビジネスコンテキスト・BUC・業務フロー・利用シーン・バリエーション/条件
Layer 3 - システム境界:   UC複合図（ユースケース・画面・イベント）
Layer 4 - システム:       情報モデル・状態モデル

参考: https://www.rdra.jp/要件定義の進め方
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
あなたはRDRA2.0（Relationship-Driven Requirements Analysis）の専門家です。
RDRA2.0の4層レイヤー構造に従い、要件定義テキストからモデル要素を抽出・構造化してください。
日本語で出力してください。英語の要件定義が渡された場合でも、出力は日本語にしてください。
"""


# ── Layer 1: システム価値 ──────────────────────────────

@dataclass
class Actor:
    """アクター（人間の利用者）"""
    name: str
    description: str = ""

@dataclass
class ExternalSystem:
    """外部システム"""
    name: str
    description: str = ""

@dataclass
class Requirement:
    """要求"""
    id: str
    description: str
    source: str           # 要求元（アクターまたは外部システム名）
    reason: str = ""      # システム化の理由


# ── Layer 2: システム外部環境 ──────────────────────────

@dataclass
class Business:
    """業務"""
    name: str
    actors: list[str] = field(default_factory=list)

@dataclass
class BusinessUseCase:
    """ビジネスユースケース（BUC）"""
    id: str
    name: str
    business: str         # 所属業務名
    actors: list[str] = field(default_factory=list)

@dataclass
class ActivityStep:
    """業務フロー/利用シーンの1ステップ"""
    step_no: int
    actor: str
    action: str
    next_step: str = ""   # 次のステップまたは分岐条件

@dataclass
class BusinessFlow:
    """業務フロー"""
    buc_id: str
    buc_name: str
    steps: list[ActivityStep] = field(default_factory=list)

@dataclass
class UsageScene:
    """利用シーン"""
    buc_id: str
    buc_name: str
    scene_name: str
    description: str = ""
    steps: list[ActivityStep] = field(default_factory=list)

@dataclass
class Variation:
    """バリエーション"""
    name: str
    values: list[str] = field(default_factory=list)

@dataclass
class Condition:
    """条件"""
    name: str
    variations: list[str] = field(default_factory=list)  # 使用するバリエーション名
    description: str = ""


# ── 生成結果 ──────────────────────────────────────────

@dataclass
class RDRAGenerationResult:
    """RDRA2.0の4層全モデル生成結果"""
    # Layer 1: システム価値
    actors: list[Actor] = field(default_factory=list)
    external_systems: list[ExternalSystem] = field(default_factory=list)
    requirements: list[Requirement] = field(default_factory=list)
    # Layer 2: システム外部環境
    businesses: list[Business] = field(default_factory=list)
    business_usecases: list[BusinessUseCase] = field(default_factory=list)
    business_flows: list[BusinessFlow] = field(default_factory=list)
    usage_scenes: list[UsageScene] = field(default_factory=list)
    variations: list[Variation] = field(default_factory=list)
    conditions: list[Condition] = field(default_factory=list)
    # Layer 3: システム境界（既存モデルと互換）
    usecases: list[Usecase] = field(default_factory=list)
    scenarios: list[OperationScenario] = field(default_factory=list)
    # Layer 4: システム
    entities: list[Entity] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    state_machines: list[EntityStateMachine] = field(default_factory=list)
    # 横断
    policies: list[BusinessPolicy] = field(default_factory=list)


class RequirementsGenerator:
    """
    RDRA2.0 の進め方に沿って要件定義テキストからモデルを生成するクラス。

    Step 1: システム価値 — アクター・外部システム・要求を特定
    Step 2: システム外部環境 — ビジネスコンテキスト・BUC を特定
    Step 3: 業務フロー / 利用シーンを作成
    Step 4: バリエーション・条件を抽出
    Step 5: システム境界 — UC複合図（ユースケース）を導出
    Step 6: システム — 情報モデル（エンティティ・リレーション）を抽出
    Step 7: システム — 状態モデルを抽出
    Step 8: 横断 — ビジネスルール（条件/バリエーション由来）を抽出
    """

    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider

    def generate(self, requirements_text: str) -> RDRAGenerationResult:
        """
        RDRA2.0 の進め方に従い、要件定義テキストからモデル一式を生成する。
        """
        result = RDRAGenerationResult()

        # Step 1: システム価値
        (result.actors, result.external_systems,
         result.requirements) = self._step1_system_value(requirements_text)

        # Step 2: システム外部環境
        (result.businesses,
         result.business_usecases) = self._step2_business_context(
            requirements_text, result.actors, result.external_systems
        )

        # Step 3: 業務フロー / 利用シーン
        (result.business_flows,
         result.usage_scenes) = self._step3_business_flows(
            requirements_text, result.business_usecases
        )

        # Step 4: バリエーション / 条件
        (result.variations,
         result.conditions) = self._step4_variations(
            requirements_text, result.business_usecases, result.business_flows
        )

        # Step 5: UC複合図 → ユースケース導出
        result.usecases = self._step5_uc_composite(
            requirements_text, result.business_usecases,
            result.business_flows, result.conditions
        )

        # Step 6: 情報モデル
        result.entities, result.relationships = self._step6_information_model(
            requirements_text, result.usecases
        )

        # Step 7: 状態モデル
        result.state_machines = self._step7_state_model(
            requirements_text, result.entities, result.usecases
        )

        # Step 8: ビジネスルール
        result.policies = self._step8_business_rules(
            requirements_text, result.entities, result.usecases,
            result.variations, result.conditions
        )

        # 操作シナリオ（業務フロー/利用シーンからUCへのマッピング）
        result.scenarios = self._derive_scenarios(
            result.usecases, result.business_flows, result.usage_scenes
        )

        return result

    # ── Step 1: システム価値 ──────────────────────────

    def _step1_system_value(
        self, requirements_text: str
    ) -> tuple[list[Actor], list[ExternalSystem], list[Requirement]]:
        user_message = f"""\
## 要件定義
{requirements_text}

---

RDRA2.0「システム価値」レイヤーとして、以下を抽出してください:
1. アクター: システムを利用する人間の役割（管理者、一般ユーザー等）
2. 外部システム: 連携する外部のシステムやサービス
3. 要求: 各アクター/外部システムがシステムに対して持つ要求（システム化の理由付き）

以下のJSON形式のみで返してください:
{{
  "actors": [
    {{"name": "管理者", "description": "システム全体を管理する"}}
  ],
  "external_systems": [
    {{"name": "決済サービス", "description": "クレジットカード決済を処理する"}}
  ],
  "requirements": [
    {{
      "id": "REQ-001",
      "description": "商品の在庫をリアルタイムに管理したい",
      "source": "管理者",
      "reason": "手作業での在庫管理では誤差が発生するため"
    }}
  ]
}}"""
        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=8192,
            )
            return self._parse_system_value(response)
        except Exception:
            return [], [], []

    def _parse_system_value(
        self, response: str
    ) -> tuple[list[Actor], list[ExternalSystem], list[Requirement]]:
        data = _extract_json(response)
        if not data:
            return [], [], []

        actors = [
            Actor(name=a.get("name", ""), description=a.get("description", ""))
            for a in data.get("actors", [])
        ]
        external_systems = [
            ExternalSystem(name=s.get("name", ""), description=s.get("description", ""))
            for s in data.get("external_systems", [])
        ]
        requirements = [
            Requirement(
                id=r.get("id", ""), description=r.get("description", ""),
                source=r.get("source", ""), reason=r.get("reason", ""),
            )
            for r in data.get("requirements", [])
        ]
        return actors, external_systems, requirements

    # ── Step 2: システム外部環境 ──────────────────────

    def _step2_business_context(
        self, requirements_text: str,
        actors: list[Actor], external_systems: list[ExternalSystem],
    ) -> tuple[list[Business], list[BusinessUseCase]]:
        actor_names = [a.name for a in actors]
        ext_names = [s.name for s in external_systems]

        user_message = f"""\
## 要件定義
{requirements_text}

## Step 1 で抽出済み
- アクター: {json.dumps(actor_names, ensure_ascii=False)}
- 外部システム: {json.dumps(ext_names, ensure_ascii=False)}

---

RDRA2.0「システム外部環境」レイヤーとして、以下を抽出してください:
1. 業務: アクターが関わる業務の単位（受注業務、顧客管理業務 等）
2. ビジネスユースケース（BUC）: 各業務内でシステムが提供する価値の単位

### ルール
- 業務にはどのアクターが関わるかを明示する
- BUCは業務に所属させる
- BUCのIDは BUC-001 形式にする

以下のJSON形式のみで返してください:
{{
  "businesses": [
    {{"name": "受注業務", "actors": ["営業担当", "顧客"]}}
  ],
  "business_usecases": [
    {{
      "id": "BUC-001",
      "name": "新規注文を受け付ける",
      "business": "受注業務",
      "actors": ["営業担当", "顧客"]
    }}
  ]
}}"""
        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=8192,
            )
            return self._parse_business_context(response)
        except Exception:
            return [], []

    def _parse_business_context(
        self, response: str
    ) -> tuple[list[Business], list[BusinessUseCase]]:
        data = _extract_json(response)
        if not data:
            return [], []

        businesses = [
            Business(name=b.get("name", ""), actors=b.get("actors", []))
            for b in data.get("businesses", [])
        ]
        bucs = [
            BusinessUseCase(
                id=b.get("id", ""), name=b.get("name", ""),
                business=b.get("business", ""), actors=b.get("actors", []),
            )
            for b in data.get("business_usecases", [])
        ]
        return businesses, bucs

    # ── Step 3: 業務フロー / 利用シーン ──────────────

    def _step3_business_flows(
        self, requirements_text: str,
        bucs: list[BusinessUseCase],
    ) -> tuple[list[BusinessFlow], list[UsageScene]]:
        if not bucs:
            return [], []

        buc_info = [
            {"id": b.id, "name": b.name, "business": b.business,
             "actors": b.actors}
            for b in bucs
        ]

        user_message = f"""\
## 要件定義
{requirements_text}

## ビジネスユースケース一覧
```json
{json.dumps(buc_info, ensure_ascii=False, indent=2)}
```

---

各BUCについて、RDRA2.0の「業務フロー」または「利用シーン」を作成してください。

### ルール
- 定型的な手順がある場合は「業務フロー」（ステップの連鎖）
- 非定型・探索的な操作の場合は「利用シーン」（シーン記述）
- 各ステップにはアクター（誰が行うか）を明記
- 1つのBUCに業務フローまたは利用シーンの少なくとも1つを作成

以下のJSON形式のみで返してください:
{{
  "business_flows": [
    {{
      "buc_id": "BUC-001",
      "buc_name": "新規注文を受け付ける",
      "steps": [
        {{"step_no": 1, "actor": "顧客", "action": "商品を選択する", "next_step": ""}},
        {{"step_no": 2, "actor": "顧客", "action": "注文内容を確認する", "next_step": ""}},
        {{"step_no": 3, "actor": "システム", "action": "在庫を確認し注文を確定する", "next_step": ""}}
      ]
    }}
  ],
  "usage_scenes": [
    {{
      "buc_id": "BUC-002",
      "buc_name": "商品を検索する",
      "scene_name": "キーワード検索で商品を探す",
      "description": "顧客がキーワードやカテゴリで商品を検索し、詳細を確認する",
      "steps": [
        {{"step_no": 1, "actor": "顧客", "action": "検索条件を入力する", "next_step": ""}},
        {{"step_no": 2, "actor": "システム", "action": "条件に合う商品一覧を表示する", "next_step": ""}}
      ]
    }}
  ]
}}"""
        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=16384,
            )
            return self._parse_business_flows(response)
        except Exception:
            return [], []

    def _parse_business_flows(
        self, response: str
    ) -> tuple[list[BusinessFlow], list[UsageScene]]:
        data = _extract_json(response)
        if not data:
            return [], []

        def _parse_steps(raw_steps: list) -> list[ActivityStep]:
            return [
                ActivityStep(
                    step_no=s.get("step_no", 0), actor=s.get("actor", ""),
                    action=s.get("action", ""), next_step=s.get("next_step", ""),
                )
                for s in raw_steps
            ]

        flows = [
            BusinessFlow(
                buc_id=f.get("buc_id", ""), buc_name=f.get("buc_name", ""),
                steps=_parse_steps(f.get("steps", [])),
            )
            for f in data.get("business_flows", [])
        ]
        scenes = [
            UsageScene(
                buc_id=s.get("buc_id", ""), buc_name=s.get("buc_name", ""),
                scene_name=s.get("scene_name", ""),
                description=s.get("description", ""),
                steps=_parse_steps(s.get("steps", [])),
            )
            for s in data.get("usage_scenes", [])
        ]
        return flows, scenes

    # ── Step 4: バリエーション / 条件 ────────────────

    def _step4_variations(
        self, requirements_text: str,
        bucs: list[BusinessUseCase],
        flows: list[BusinessFlow],
    ) -> tuple[list[Variation], list[Condition]]:
        buc_names = [b.name for b in bucs]
        flow_summaries = [
            {"buc": f.buc_name,
             "actions": [s.action for s in f.steps]}
            for f in flows
        ]

        user_message = f"""\
## 要件定義
{requirements_text}

## BUC一覧
{json.dumps(buc_names, ensure_ascii=False)}

## 業務フロー概要
```json
{json.dumps(flow_summaries, ensure_ascii=False, indent=2)}
```

---

RDRA2.0の「バリエーション」と「条件」を抽出してください。

### 定義
- バリエーション: 業務の中で値が変わる項目（会員種別、支払方法、配送方法 等）
- 条件: バリエーションの組み合わせで業務の振る舞いが変わるルール

以下のJSON形式のみで返してください:
{{
  "variations": [
    {{"name": "会員種別", "values": ["一般", "プレミアム", "法人"]}},
    {{"name": "支払方法", "values": ["クレジットカード", "銀行振込", "代金引換"]}}
  ],
  "conditions": [
    {{
      "name": "送料無料条件",
      "variations": ["会員種別", "注文金額"],
      "description": "プレミアム会員または注文金額5000円以上で送料無料"
    }}
  ]
}}"""
        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=SYSTEM_PROMPT,
                max_tokens=8192,
            )
            return self._parse_variations(response)
        except Exception:
            return [], []

    def _parse_variations(
        self, response: str
    ) -> tuple[list[Variation], list[Condition]]:
        data = _extract_json(response)
        if not data:
            return [], []

        variations = [
            Variation(name=v.get("name", ""), values=v.get("values", []))
            for v in data.get("variations", [])
        ]
        conditions = [
            Condition(
                name=c.get("name", ""),
                variations=c.get("variations", []),
                description=c.get("description", ""),
            )
            for c in data.get("conditions", [])
        ]
        return variations, conditions

    # ── Step 5: UC複合図 ─────────────────────────────

    def _step5_uc_composite(
        self, requirements_text: str,
        bucs: list[BusinessUseCase],
        flows: list[BusinessFlow],
        conditions: list[Condition],
    ) -> list[Usecase]:
        buc_info = [
            {"id": b.id, "name": b.name, "business": b.business,
             "actors": b.actors}
            for b in bucs
        ]
        flow_info = [
            {"buc_id": f.buc_id, "buc_name": f.buc_name,
             "steps": [s.action for s in f.steps]}
            for f in flows
        ]
        cond_info = [
            {"name": c.name, "description": c.description}
            for c in conditions
        ]

        user_message = f"""\
## 要件定義
{requirements_text}

## BUC一覧
```json
{json.dumps(buc_info, ensure_ascii=False, indent=2)}
```

## 業務フロー
```json
{json.dumps(flow_info, ensure_ascii=False, indent=2)}
```

## 条件
```json
{json.dumps(cond_info, ensure_ascii=False, indent=2)}
```

---

RDRA2.0「システム境界」レイヤーとして、UC複合図のユースケースを導出してください。

### ルール
- BUCと業務フローからシステムが担うユースケース（UC）を導出する
- 各UCにはアクター・事前条件・事後条件・関連エンティティ名を設定
- カテゴリはBUCの所属業務名を使う
- UCのIDは UC-001 形式にする
- 優先度を high/medium/low で設定

以下のJSON形式のみで返してください:
{{
  "usecases": [
    {{
      "id": "UC-001",
      "name": "商品を注文する",
      "actor": "顧客",
      "description": "選択した商品を注文し決済を完了する",
      "preconditions": ["顧客がログイン済みであること", "カートに商品が入っていること"],
      "postconditions": ["注文が確定される", "在庫が減算される"],
      "related_entities": ["注文", "商品", "顧客"],
      "category": "受注業務",
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
        data = _extract_json(response)
        if not data:
            return []

        return [
            Usecase(
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
            )
            for item in data.get("usecases", [])
        ]

    # ── Step 6: 情報モデル ───────────────────────────

    def _step6_information_model(
        self, requirements_text: str, usecases: list[Usecase],
    ) -> tuple[list[Entity], list[Relationship]]:
        uc_entities = sorted({
            e for uc in usecases for e in uc.related_entities
        })

        user_message = f"""\
## 要件定義
{requirements_text}

## ユースケースから参照されているエンティティ名
{json.dumps(uc_entities, ensure_ascii=False)}

---

RDRA2.0「システム」レイヤーの情報モデルを作成してください。

### ルール
1. UCから参照されるエンティティを中心に、ドメインの主要概念をエンティティとして定義する
2. 各エンティティには主要属性（5〜10個）を特定する
3. エンティティ間の関係を「1-1」「1-N」「N-N」で分類する
4. システム内部用エンティティ（セッション、ログ等）は除外する

以下のJSON形式のみで返してください:
{{
  "entities": [
    {{
      "name": "注文",
      "class_name": "Order",
      "table_name": "orders",
      "attributes": ["注文番号", "注文日時", "合計金額", "ステータス", "配送先住所"],
      "description": "顧客が行った注文"
    }}
  ],
  "relationships": [
    {{
      "from_entity": "顧客",
      "to_entity": "注文",
      "relation_type": "1-N",
      "label": "注文する"
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
        data = _extract_json(response)
        if not data:
            return [], []

        entities = [
            Entity(
                name=item.get("name", ""),
                class_name=item.get("class_name", ""),
                table_name=item.get("table_name", ""),
                attributes=item.get("attributes", []),
                description=item.get("description", ""),
            )
            for item in data.get("entities", [])
        ]
        relationships = [
            Relationship(
                from_entity=item.get("from_entity", ""),
                to_entity=item.get("to_entity", ""),
                relation_type=item.get("relation_type", "1-N"),
                label=item.get("label", ""),
            )
            for item in data.get("relationships", [])
        ]
        return entities, relationships

    # ── Step 7: 状態モデル ───────────────────────────

    def _step7_state_model(
        self, requirements_text: str,
        entities: list[Entity], usecases: list[Usecase],
    ) -> list[EntityStateMachine]:
        if not entities:
            return []

        entity_info = [
            {"name": e.name, "class_name": e.class_name,
             "attributes": e.attributes}
            for e in entities
        ]
        uc_names = [f"{uc.id}: {uc.name}" for uc in usecases]

        user_message = f"""\
## 要件定義
{requirements_text}

## エンティティ一覧
```json
{json.dumps(entity_info, ensure_ascii=False, indent=2)}
```

## ユースケース一覧
{json.dumps(uc_names, ensure_ascii=False)}

---

RDRA2.0「システム」レイヤーの状態モデルを作成してください。

### ルール
1. 状態（ステータス）を持つエンティティのみ抽出する
2. 各状態遷移にはトリガー（どのUCで遷移するか）を明記する
3. 初期状態と最終状態を指定する
4. ガード条件がある場合は記述する
5. 該当エンティティがなければ空配列を返す

以下のJSON形式のみで返してください:
{{
  "state_machines": [
    {{
      "entity_name": "注文",
      "entity_class": "Order",
      "state_field": "status",
      "states": ["下書き", "確定", "出荷済み", "配達完了", "キャンセル"],
      "transitions": [
        {{"from_state": "下書き", "to_state": "確定", "trigger": "注文確定（UC-001）", "guard": "在庫あり"}}
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
        data = _extract_json(response)
        if not data:
            return []

        machines: list[EntityStateMachine] = []
        for item in data.get("state_machines", []):
            transitions = [
                StateTransition(
                    entity_name=item.get("entity_name", ""),
                    from_state=t.get("from_state", ""),
                    to_state=t.get("to_state", ""),
                    trigger=t.get("trigger", ""),
                    guard=t.get("guard", ""),
                )
                for t in item.get("transitions", [])
            ]
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

    # ── Step 8: ビジネスルール ────────────────────────

    def _step8_business_rules(
        self, requirements_text: str,
        entities: list[Entity], usecases: list[Usecase],
        variations: list[Variation], conditions: list[Condition],
    ) -> list[BusinessPolicy]:
        entity_names = [e.name for e in entities]
        uc_ids = [uc.id for uc in usecases]
        var_info = [{"name": v.name, "values": v.values} for v in variations]
        cond_info = [
            {"name": c.name, "description": c.description}
            for c in conditions
        ]

        user_message = f"""\
## 要件定義
{requirements_text}

## 抽出済みエンティティ
{json.dumps(entity_names, ensure_ascii=False)}

## 抽出済みユースケースID
{json.dumps(uc_ids, ensure_ascii=False)}

## バリエーション
```json
{json.dumps(var_info, ensure_ascii=False, indent=2)}
```

## 条件
```json
{json.dumps(cond_info, ensure_ascii=False, indent=2)}
```

---

上記のバリエーション・条件および要件定義から、ビジネスルールを抽出してください。
条件はバリエーションの組み合わせから導出されるルールです。

### カテゴリ
1. バリデーション（入力制約、形式チェック）
2. 認可（アクセス制御、権限）
3. 計算（料金計算、集計ロジック）
4. 制約（一意性制約、排他制御）
5. ワークフロー（承認フロー、段階的処理）

IDは BP-001 形式、重要度は must/should/may で設定してください。

以下のJSON形式のみで返してください:
{{
  "policies": [
    {{
      "id": "BP-001",
      "name": "プレミアム会員送料無料",
      "category": "計算",
      "description": "プレミアム会員は送料が無料になる",
      "related_entities": ["注文", "会員"],
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
        data = _extract_json(response)
        if not data:
            return []

        return [
            BusinessPolicy(
                id=item.get("id", ""),
                name=item.get("name", ""),
                category=item.get("category", ""),
                description=item.get("description", ""),
                related_entities=item.get("related_entities", []),
                related_usecases=item.get("related_usecases", []),
                severity=item.get("severity", "must"),
            )
            for item in data.get("policies", [])
        ]

    # ── 操作シナリオ導出 ─────────────────────────────

    def _derive_scenarios(
        self,
        usecases: list[Usecase],
        flows: list[BusinessFlow],
        scenes: list[UsageScene],
    ) -> list[OperationScenario]:
        """業務フロー/利用シーンからUCに紐づく操作シナリオを導出する"""
        scenarios: list[OperationScenario] = []
        uc_map = {uc.id: uc for uc in usecases}

        # BUC → UC のマッピング（カテゴリ名＝業務名で紐づけ）
        buc_to_ucs: dict[str, list[Usecase]] = {}
        for uc in usecases:
            buc_to_ucs.setdefault(uc.category, []).append(uc)

        sc_counter = 0

        for flow in flows:
            related_ucs = buc_to_ucs.get(
                _find_business_for_buc(flow.buc_name, flows, scenes), []
            )
            if not related_ucs:
                related_ucs = usecases[:1] if usecases else []

            for uc in related_ucs:
                sc_counter += 1
                steps = [
                    OperationStep(
                        step_no=s.step_no, actor=s.actor,
                        action=s.action, expected_result="",
                    )
                    for s in flow.steps
                ]
                scenarios.append(OperationScenario(
                    usecase_id=uc.id,
                    usecase_name=uc.name,
                    scenario_id=f"SC-{sc_counter:03d}-01",
                    scenario_name=f"業務フロー: {flow.buc_name}",
                    scenario_type="normal",
                    steps=steps,
                    variations=[],
                ))
                break  # 1BUC→1UCで十分

        for scene in scenes:
            sc_counter += 1
            steps = [
                OperationStep(
                    step_no=s.step_no, actor=s.actor,
                    action=s.action, expected_result="",
                )
                for s in scene.steps
            ]
            # 利用シーンに最も近いUCを探す
            target_uc = usecases[0] if usecases else None
            for uc in usecases:
                if uc.category and uc.category in scene.buc_name:
                    target_uc = uc
                    break

            if target_uc:
                scenarios.append(OperationScenario(
                    usecase_id=target_uc.id,
                    usecase_name=target_uc.name,
                    scenario_id=f"SC-{sc_counter:03d}-01",
                    scenario_name=f"利用シーン: {scene.scene_name}",
                    scenario_type="normal",
                    steps=steps,
                    variations=[],
                ))

        return scenarios


def _find_business_for_buc(
    buc_name: str,
    flows: list[BusinessFlow],
    scenes: list[UsageScene],
) -> str:
    """BUC名から業務名を推定する（簡易マッチ）"""
    for f in flows:
        if f.buc_name == buc_name:
            return f.buc_name
    return buc_name


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
