"""
情報モデル生成モジュール

データモデルの解析結果から RDRA の情報モデルを生成する。
- エンティティ単位: Mermaid ER図として出力
- ユースケース単位: 関連エンティティをグループ化した概要図として出力

言語・フレームワーク非依存: LLM で日本語名・リレーション種別を動的に推定する。
"""

import json
import re
from dataclasses import dataclass, field

from llm.provider import LLMProvider
from analyzer.source_parser import ParsedModel


@dataclass
class Entity:
    """情報モデルのエンティティ"""
    name: str                       # エンティティ名（日本語）
    class_name: str                 # モデルのクラス名
    table_name: str = ""            # DBテーブル名（不明時は空文字）
    attributes: list[str] = field(default_factory=list)
    primary_key: str = "id"
    description: str = ""


@dataclass
class Relationship:
    """エンティティ間のリレーション"""
    from_entity: str        # 関係元エンティティ名
    to_entity: str          # 関係先エンティティ名
    relation_type: str      # "1-1" | "1-N" | "N-N"
    label: str              # リレーションのラベル（日本語）
    orm_type: str = ""      # ORM固有の種別（hasMany, belongs_to, OneToMany 等）


@dataclass
class InformationGroup:
    """ユースケース単位の情報グループ"""
    usecase_id: str
    usecase_name: str
    actor: str
    entities: list[Entity] = field(default_factory=list)
    internal_relationships: list[Relationship] = field(default_factory=list)


class InformationModelGenerator:
    """
    データモデルから情報モデルを生成するクラス。

    LLM を使ってモデル名の日本語化・リレーション種別の推定を行う。
    Mermaid ER図形式で出力する。
    """

    def __init__(self, llm_provider: LLMProvider, project_context: str = ""):
        self._llm = llm_provider
        self._project_context = project_context

    def generate(self, models: list[ParsedModel]) -> tuple[list[Entity], list[Relationship]]:
        """
        データモデル一覧から情報モデルを生成する。

        Args:
            models: 解析済みデータモデル一覧

        Returns:
            tuple[list[Entity], list[Relationship]]: エンティティとリレーションのタプル
        """
        # LLM でモデル名の日本語化とエンティティ生成
        if self._llm and models:
            entities, relationships = self._generate_with_llm(models)
        else:
            entities = self._create_entities_fallback(models)
            relationships = self._extract_relationships_fallback(models, entities)

        return entities, relationships

    def _generate_with_llm(
        self, models: list[ParsedModel]
    ) -> tuple[list[Entity], list[Relationship]]:
        """LLM でエンティティ名の日本語化とリレーション推定を行う"""
        models_info = []
        for m in models[:100]:
            models_info.append({
                "class_name": m.class_name,
                "table_name": m.table_name,
                "fields": m.fillable[:15],
                "relationships": m.relationships[:10],
            })

        context_part = ""
        if self._project_context:
            context_part = f"""
## プロジェクトコンテキスト
{self._project_context}
"""

        system_prompt = "あなたはRDRA（Relationship-Driven Requirements Analysis）の専門家です。"

        user_message = f"""{context_part}

## データモデル一覧
```json
{json.dumps(models_info, ensure_ascii=False, indent=2)}
```

上記のデータモデルについて、以下を行ってください:
1. 各モデルに適切な日本語名をつける（プロジェクトのドメインに合わせて）
2. システム内部用のモデル（認証トークン、ログ、マイグレーション等）を除外する
3. リレーション定義から、エンティティ間の関係を「1-1」「1-N」「N-N」で分類する

以下のJSON形式のみで返してください:
{{
  "entities": [
    {{
      "class_name": "User",
      "japanese_name": "ユーザー",
      "description": "システムを利用するユーザー",
      "exclude": false
    }}
  ],
  "relationships": [
    {{
      "from": "User",
      "to": "Post",
      "type": "1-N",
      "label": "投稿する"
    }}
  ]
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=system_prompt,
            )
            return self._parse_llm_result(response, models)
        except Exception:
            entities = self._create_entities_fallback(models)
            relationships = self._extract_relationships_fallback(models, entities)
            return entities, relationships

    def _parse_llm_result(
        self, response: str, models: list[ParsedModel]
    ) -> tuple[list[Entity], list[Relationship]]:
        """LLM レスポンスをパースしてエンティティとリレーションを構築する"""
        cleaned = re.sub(r"```(?:json)?\s*", "", response).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            entities = self._create_entities_fallback(models)
            relationships = self._extract_relationships_fallback(models, entities)
            return entities, relationships

        data = json.loads(json_match.group(0))

        # クラス名→日本語名のマッピングを構築
        name_map: dict[str, str] = {}
        excluded: set[str] = set()
        desc_map: dict[str, str] = {}
        for item in data.get("entities", []):
            cn = item.get("class_name", "")
            if item.get("exclude", False):
                excluded.add(cn)
            else:
                name_map[cn] = item.get("japanese_name", cn)
                desc_map[cn] = item.get("description", "")

        # モデル→エンティティに変換
        model_map = {m.class_name: m for m in models}
        entities: list[Entity] = []
        for class_name, japanese_name in name_map.items():
            model = model_map.get(class_name)
            attributes = model.fillable[:15] if model else []
            table_name = model.table_name if model else ""
            entities.append(Entity(
                name=japanese_name,
                class_name=class_name,
                table_name=table_name,
                attributes=attributes,
                description=desc_map.get(class_name, ""),
            ))

        # リレーション構築
        relationships: list[Relationship] = []
        for rel_item in data.get("relationships", []):
            from_class = rel_item.get("from", "")
            to_class = rel_item.get("to", "")
            if from_class in excluded or to_class in excluded:
                continue
            from_name = name_map.get(from_class, from_class)
            to_name = name_map.get(to_class, to_class)
            relationships.append(Relationship(
                from_entity=from_name,
                to_entity=to_name,
                relation_type=rel_item.get("type", "1-N"),
                label=rel_item.get("label", "関連する"),
            ))

        return entities, relationships

    def _create_entities_fallback(self, models: list[ParsedModel]) -> list[Entity]:
        """LLM なしのフォールバック: クラス名をそのままエンティティ名として使用"""
        entities: list[Entity] = []

        for model in models:
            attributes = list(model.fillable)
            if not attributes:
                attributes = list(model.casts.keys())

            entities.append(Entity(
                name=model.class_name,
                class_name=model.class_name,
                table_name=model.table_name,
                attributes=attributes[:15],
            ))

        return entities

    def _extract_relationships_fallback(
        self,
        models: list[ParsedModel],
        entities: list[Entity],
    ) -> list[Relationship]:
        """LLM なしのフォールバック: リレーション文字列をパースして関係を抽出"""
        relationships: list[Relationship] = []
        class_to_entity = {e.class_name: e.name for e in entities}

        for model in models:
            from_entity = class_to_entity.get(model.class_name, model.class_name)

            for rel_str in model.relationships:
                rel_match = re.match(r"(\w+)\s+\((\w+)\)", rel_str)
                if not rel_match:
                    continue

                rel_method = rel_match.group(1)
                orm_type = rel_match.group(2)

                to_class = self._method_to_class(rel_method)
                to_entity = class_to_entity.get(to_class, to_class)

                relation_type, label = self._infer_relation_type(orm_type)

                if from_entity == to_entity or not to_entity:
                    continue

                existing = any(
                    r.from_entity == from_entity and r.to_entity == to_entity
                    for r in relationships
                )
                if not existing:
                    relationships.append(Relationship(
                        from_entity=from_entity,
                        to_entity=to_entity,
                        relation_type=relation_type,
                        label=label,
                        orm_type=orm_type,
                    ))

        return relationships

    def _method_to_class(self, method_name: str) -> str:
        """リレーションメソッド名からクラス名を推定する"""
        words = re.findall(r"[A-Z][a-z]*|[a-z]+", method_name)
        if not words:
            return method_name
        class_parts = [w.capitalize() for w in words]
        class_name = "".join(class_parts)
        if class_name.endswith("s") and len(class_name) > 1:
            class_name = class_name[:-1]
        return class_name

    def _infer_relation_type(self, orm_type: str) -> tuple[str, str]:
        """ORM種別から汎用的にリレーション情報を推定する"""
        orm_lower = orm_type.lower()

        # 多対多
        if any(kw in orm_lower for kw in ["manytomany", "belongstomany", "has_and_belongs_to_many", "n-n"]):
            return ("N-N", "関連する")

        # 一対一
        if any(kw in orm_lower for kw in ["hasone", "has_one", "onetoone", "1-1"]):
            return ("1-1", "持つ")

        # 多対一（belongsTo系）
        if any(kw in orm_lower for kw in ["belongsto", "belongs_to", "manytoone"]):
            return ("N-1", "属する")

        # 一対多（デフォルト）
        if any(kw in orm_lower for kw in ["hasmany", "has_many", "onetomany", "morphmany"]):
            return ("1-N", "持つ")

        # polymorphic
        if "morph" in orm_lower:
            return ("1-N", "ポリモーフィック")

        return ("1-N", "関連する")

    # CREATE/UPDATE 操作を示すHTTPメソッド
    _CU_METHODS = {"POST", "PUT", "PATCH"}

    # CREATE/UPDATE 操作を示すキーワード（ユースケース名・説明に含まれるか判定）
    _CU_KEYWORDS = re.compile(
        r"登録|作成|追加|新規|更新|編集|変更|設定|保存|"
        r"create|register|add|new|update|edit|modify|save|store|upsert",
        re.IGNORECASE,
    )

    def _is_create_or_update_usecase(self, uc) -> bool:
        """ユースケースがCREATEまたはUPDATE操作を含むか判定する"""
        # 1. related_routes に POST/PUT/PATCH があるか
        for route in getattr(uc, "related_routes", []):
            method = route.split()[0].upper() if " " in route else ""
            if method in self._CU_METHODS:
                return True

        # 2. ユースケース名・説明にCU系キーワードがあるか
        text = f"{getattr(uc, 'name', '')} {getattr(uc, 'description', '')}"
        if self._CU_KEYWORDS.search(text):
            return True

        return False

    def group_by_usecase(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
        usecases: list,
    ) -> list[InformationGroup]:
        """
        CREATE/UPDATE 系ユースケースの related_entities を使い、
        エンティティをグループ化する。

        データを生成・更新するユースケースこそが情報の構造を定義するため、
        検索・参照系のユースケースは対象外とする。
        """
        # class_name / name どちらでも引けるようにマップ構築
        entity_by_class = {e.class_name: e for e in entities}
        entity_by_name = {e.name: e for e in entities}

        groups: list[InformationGroup] = []

        for uc in usecases:
            if not self._is_create_or_update_usecase(uc):
                continue

            matched: list[Entity] = []
            for ref in getattr(uc, "related_entities", []):
                entity = entity_by_class.get(ref) or entity_by_name.get(ref)
                if entity and entity not in matched:
                    matched.append(entity)

            if not matched:
                continue

            # グループ内のリレーションを抽出
            matched_names = {e.name for e in matched}
            internal_rels = [
                r for r in relationships
                if r.from_entity in matched_names and r.to_entity in matched_names
            ]

            groups.append(InformationGroup(
                usecase_id=uc.id,
                usecase_name=uc.name,
                actor=uc.actor,
                entities=matched,
                internal_relationships=internal_rels,
            ))

        return groups

    def to_mermaid_grouped(self, groups: list[InformationGroup]) -> str:
        """
        ユースケース単位でグループ化した情報モデル概要図を Mermaid flowchart で出力する。
        """
        lines = ["flowchart LR"]

        # エンティティが属するグループを把握（重複所属あり）
        for g in groups:
            safe_uc = re.sub(r"[^\w]", "_", g.usecase_id)
            entity_labels = "<br>".join(
                [self._safe_mermaid_text(e.name) for e in g.entities]
            )
            lines.append(
                f'    subgraph {safe_uc}["{self._safe_mermaid_text(g.usecase_name)}"]'
            )
            for e in g.entities:
                safe_e = re.sub(r"[^\w]", "_", f"{safe_uc}_{e.class_name}")
                lines.append(f'        {safe_e}["{self._safe_mermaid_text(e.name)}"]')
            # グループ内リレーション
            for r in g.internal_relationships:
                from_e = next((e for e in g.entities if e.name == r.from_entity), None)
                to_e = next((e for e in g.entities if e.name == r.to_entity), None)
                if from_e and to_e:
                    safe_from = re.sub(r"[^\w]", "_", f"{safe_uc}_{from_e.class_name}")
                    safe_to = re.sub(r"[^\w]", "_", f"{safe_uc}_{to_e.class_name}")
                    lines.append(f'        {safe_from} -->|{self._safe_mermaid_text(r.label)}| {safe_to}')
            lines.append("    end")

        # アクターからユースケースへの接続
        actors_seen: set[str] = set()
        for g in groups:
            safe_uc = re.sub(r"[^\w]", "_", g.usecase_id)
            safe_actor = re.sub(r"[^\w]", "_", f"actor_{g.actor}")
            if safe_actor not in actors_seen:
                lines.append(f'    {safe_actor}(("{self._safe_mermaid_text(g.actor)}"))')
                actors_seen.add(safe_actor)
            lines.append(f'    {safe_actor} --> {safe_uc}')

        # スタイル
        lines.append("")
        for actor_id in actors_seen:
            lines.append(f"    style {actor_id} fill:#f9f,stroke:#333")

        return "\n".join(lines)

    @staticmethod
    def _safe_mermaid_text(text: str) -> str:
        """Mermaid で安全な文字列に変換"""
        text = text.replace('"', "'")
        if len(text) > 40:
            text = text[:37] + "..."
        return text

    def to_mermaid(
        self, entities: list[Entity], relationships: list[Relationship]
    ) -> str:
        """
        エンティティとリレーションを Mermaid ER図記法に変換する。
        """
        lines = ["erDiagram"]

        for entity in entities:
            safe_name = entity.class_name
            lines.append(f"    {safe_name} {{")
            lines.append(f"        string id PK")
            for attr in entity.attributes[:10]:
                safe_attr = re.sub(r"[^a-zA-Z0-9_]", "_", attr)
                lines.append(f"        string {safe_attr}")
            lines.append(f"    }}")
            lines.append("")

        for rel in relationships:
            from_class = self._entity_to_class(rel.from_entity, entities)
            to_class = self._entity_to_class(rel.to_entity, entities)
            if not from_class or not to_class:
                continue
            mermaid_rel = self._to_mermaid_relation(rel.relation_type)
            # erDiagram のラベルは ASCII のみ許容。日本語は引用符で囲む
            label = rel.label.replace('"', "'").replace(" ", "_")
            lines.append(f'    {from_class} {mermaid_rel} {to_class} : "{label}"')

        return "\n".join(lines)

    def _entity_to_class(self, entity_name: str, entities: list[Entity]) -> str:
        """エンティティ名からクラス名を取得する"""
        for e in entities:
            if e.name == entity_name:
                return e.class_name
        return ""

    def _to_mermaid_relation(self, relation_type: str) -> str:
        """リレーション種別をMermaid記法に変換する"""
        return {
            "1-1": "||--||",
            "1-N": "||--o{",
            "N-1": "}o--||",
            "N-N": "}o--o{",
        }.get(relation_type, "||--o{")
