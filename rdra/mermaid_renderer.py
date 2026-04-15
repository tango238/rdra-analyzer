"""
Mermaid記法出力レンダラー

RDRA の全ダイアグラムを Markdown ファイルとして出力する。
"""

import json
from pathlib import Path
from datetime import datetime

from analyzer.usecase_extractor import Usecase
from analyzer.scenario_builder import OperationScenario
from .information_model import Entity, Relationship, InformationGroup, InformationModelGenerator
from .usecase_diagram import UsecaseDiagramGenerator
from .activity_diagram import ActivityDiagramGenerator
from .state_transition import StateTransitionGenerator, EntityStateMachine
from .business_policy import BusinessPolicyExtractor, BusinessPolicy
from .viewer_template import generate_viewer_html


class MermaidRenderer:
    """
    RDRA ダイアグラムを Mermaid 記法の Markdown ファイルとして出力するクラス。

    出力ファイル:
    - output/rdra/information_model.md    : 情報モデル（ER図）
    - output/rdra/usecase_diagram.md      : ユースケース複合図
    - output/rdra/usecase_conditions.md   : ユースケース条件図
    - output/rdra/scenarios_overview.md   : 操作シナリオ概要図
    - output/rdra/scenario_*.md           : 個別シナリオのシーケンス図
    - output/rdra/state_transitions.md    : 状態遷移図
    - output/rdra/business_policies.md    : ビジネスポリシー一覧
    - output/rdra/index.md               : インデックス（全体概要）
    """

    def __init__(
        self,
        info_model_gen: InformationModelGenerator,
        usecase_diagram_gen: UsecaseDiagramGenerator,
        activity_diagram_gen: ActivityDiagramGenerator,
        state_transition_gen: StateTransitionGenerator = None,
        business_policy_ext: BusinessPolicyExtractor = None,
        project_name: str = "",
    ):
        self._info_model_gen = info_model_gen
        self._uc_diagram_gen = usecase_diagram_gen
        self._activity_gen = activity_diagram_gen
        self._state_gen = state_transition_gen
        self._bp_ext = business_policy_ext
        self._project_name = project_name

    def render_all(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
        usecases: list[Usecase],
        scenarios: list[OperationScenario],
        output_dir: Path,
        routes: list = None,
        controllers: list = None,
    ) -> list[str]:
        """
        全 RDRA ダイアグラムを Markdown ファイルとして出力する。

        Args:
            entities: 情報モデルのエンティティ一覧
            relationships: エンティティ間のリレーション一覧
            usecases: ユースケース一覧
            scenarios: 操作シナリオ一覧
            output_dir: 出力ディレクトリ

        Returns:
            list[str]: 生成されたファイルパスの一覧
        """
        rdra_dir = output_dir / "rdra"
        rdra_dir.mkdir(parents=True, exist_ok=True)

        saved_files: list[str] = []
        mermaid_sources: dict[str, str] = {}

        # 1a. 情報モデル（ER図 - エンティティ単位）
        mermaid_sources["information_model"] = self._info_model_gen.to_mermaid(entities, relationships)
        info_model_path = self._render_information_model(
            entities, relationships, rdra_dir
        )
        saved_files.append(info_model_path)

        # 1b. 情報モデル概要（ユースケース単位）
        groups = self._info_model_gen.group_by_usecase(entities, relationships, usecases)
        if groups:
            mermaid_sources["information_model_grouped"] = self._info_model_gen.to_mermaid_grouped(groups)
            grouped_path = self._render_information_model_grouped(
                groups, rdra_dir
            )
            saved_files.append(grouped_path)

        # 2. ユースケース複合図
        mermaid_sources["usecase_diagram"] = self._uc_diagram_gen.generate_mermaid(usecases)
        uc_diagram_path = self._render_usecase_diagram(usecases, rdra_dir)
        saved_files.append(uc_diagram_path)

        # 3. ユースケース条件図
        mermaid_sources["usecase_conditions"] = self._uc_diagram_gen.generate_conditions_mermaid(usecases)
        for uc in usecases:
            mermaid_sources[f"uc_condition_{uc.id}"] = self._uc_diagram_gen.generate_single_condition_mermaid(uc)
        uc_cond_path = self._render_usecase_conditions(usecases, rdra_dir)
        saved_files.append(uc_cond_path)

        # 4. アクティビティ図（操作シナリオ）
        # シナリオ概要
        mermaid_sources["scenarios_overview"] = self._activity_gen.generate_all_scenarios_flowchart(scenarios)
        # 個別シナリオ（ユースケースのアクター名を引き渡し）
        uc_actor_map = {uc.id: uc.actor for uc in usecases} if usecases else {}
        for sc in scenarios:
            key = f"scenario_{sc.scenario_id}"
            actor_name = uc_actor_map.get(sc.usecase_id, "")
            mermaid_sources[key] = self._activity_gen.generate_sequence_diagram(sc, actor_name=actor_name)
        activity_files = self._activity_gen.save_all(scenarios, rdra_dir / "activities", uc_actor_map=uc_actor_map)
        saved_files.extend(activity_files)

        # 5. 状態遷移図
        state_machines = []
        if self._state_gen:
            state_machines = self._state_gen.generate(entities, routes, usecases)
            if state_machines:
                for m in state_machines:
                    mermaid_sources[f"state_{m.entity_class}"] = self._state_gen.to_mermaid(m)
                st_path = self._render_state_transitions(state_machines, rdra_dir)
                saved_files.append(st_path)

        # 6. ビジネスポリシー一覧
        policies = []
        if self._bp_ext:
            policies = self._bp_ext.extract(
                entities, usecases, routes, controllers,
            )
            if policies:
                bp_path = self._render_business_policies(policies, rdra_dir)
                saved_files.append(bp_path)

        # 7. インデックスページ
        index_path = self._render_index(
            entities, usecases, scenarios, saved_files, rdra_dir,
            state_machines=state_machines,
            policies=policies,
        )
        saved_files.append(index_path)

        # 8. インタラクティブビューワー
        viewer_path = self._render_viewer(
            entities, relationships, usecases, scenarios,
            groups, state_machines, policies,
            mermaid_sources, rdra_dir,
        )
        saved_files.append(viewer_path)

        return saved_files

    def _render_viewer(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
        usecases: list[Usecase],
        scenarios: list[OperationScenario],
        groups: list[InformationGroup],
        state_machines: list[EntityStateMachine],
        policies: list[BusinessPolicy],
        mermaid_sources: dict[str, str],
        rdra_dir: Path,
        screen_specs: list = None,
    ) -> str:
        """インタラクティブビューワー HTML を生成する"""
        generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # データをJSON化
        data = {
            "entities": [
                {"name": e.name, "class_name": e.class_name, "table_name": e.table_name,
                 "attributes": e.attributes[:15], "description": e.description}
                for e in entities
            ],
            "relationships": [
                {"from_entity": r.from_entity, "to_entity": r.to_entity,
                 "relation_type": r.relation_type, "label": r.label}
                for r in relationships
            ],
            "usecases": [
                {"id": uc.id, "name": uc.name, "actor": uc.actor,
                 "description": uc.description,
                 "preconditions": uc.preconditions, "postconditions": uc.postconditions,
                 "related_routes": uc.related_routes[:10],
                 "related_entities": uc.related_entities,
                 "related_controllers": getattr(uc, "related_controllers", []),
                 "related_views": getattr(uc, "related_views", []),
                 "category": uc.category, "priority": uc.priority}
                for uc in usecases
            ],
            "scenarios": [
                {"usecase_id": sc.usecase_id, "usecase_name": sc.usecase_name,
                 "scenario_id": sc.scenario_id, "scenario_name": sc.scenario_name,
                 "scenario_type": sc.scenario_type,
                 "steps": [
                     {"step_no": st.step_no, "actor": st.actor,
                      "action": st.action, "expected_result": st.expected_result}
                     for st in sc.steps
                 ]}
                for sc in scenarios
            ],
            "state_machines": [
                {"entity_name": m.entity_name, "entity_class": m.entity_class,
                 "state_field": m.state_field, "states": m.states,
                 "transitions": [
                     {"from_state": t.from_state, "to_state": t.to_state,
                      "trigger": t.trigger, "guard": t.guard}
                     for t in m.transitions
                 ],
                 "initial_state": m.initial_state, "final_states": m.final_states}
                for m in state_machines
            ],
            "policies": [
                {"id": bp.id, "name": bp.name, "category": bp.category,
                 "description": bp.description,
                 "related_entities": bp.related_entities,
                 "related_usecases": bp.related_usecases,
                 "severity": bp.severity,
                 "code_references": [
                     {"file_path": ref.file_path, "description": ref.description, "code_type": ref.code_type}
                     for ref in (bp.code_references if hasattr(bp, "code_references") else [])
                 ]}
                for bp in policies
            ],
            "information_groups": [
                {"usecase_id": g.usecase_id, "usecase_name": g.usecase_name,
                 "actor": g.actor,
                 "entities": [e.name for e in g.entities]}
                for g in (groups or [])
            ],
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
        }

        data_json = json.dumps(data, ensure_ascii=False)
        mermaid_json = json.dumps(mermaid_sources, ensure_ascii=False)

        html = generate_viewer_html(
            project_name="RDRA Analysis",
            generated_at=generated_at,
            data_json=data_json,
            mermaid_sources=mermaid_json,
        )

        file_path = rdra_dir / "viewer.html"
        file_path.write_text(html, encoding="utf-8")
        return str(file_path)

    def _render_information_model(
        self,
        entities: list[Entity],
        relationships: list[Relationship],
        rdra_dir: Path,
    ) -> str:
        """情報モデルのMarkdownファイルを生成する"""
        mermaid_content = self._info_model_gen.to_mermaid(entities, relationships)

        entity_list = "\n".join([
            f"| {e.class_name} | {e.name} | {e.table_name} | "
            f"{', '.join(e.attributes[:5])} |"
            for e in entities
        ])

        content = f"""# 情報モデル

生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
エンティティ数: {len(entities)} | リレーション数: {len(relationships)}

## ER図

```mermaid
{mermaid_content}
```

## エンティティ一覧

| クラス名 | 日本語名 | テーブル名 | 主要属性 |
|---------|---------|-----------|---------|
{entity_list}

## リレーション一覧

| 関係元 | 種別 | 関係先 | ORMメソッド |
|-------|-----|-------|-----------|
{chr(10).join([
    f"| {r.from_entity} | {r.relation_type} | {r.to_entity} | {r.orm_type} |"
    for r in relationships
])}
"""
        file_path = rdra_dir / "information_model.md"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def _render_information_model_grouped(
        self,
        groups: list[InformationGroup],
        rdra_dir: Path,
    ) -> str:
        """ユースケース単位の情報モデル概要図を生成する"""
        mermaid_content = self._info_model_gen.to_mermaid_grouped(groups)

        # グループ一覧テーブル
        group_rows = "\n".join([
            f"| {g.usecase_id} | {g.usecase_name} | {g.actor} | "
            f"{', '.join(e.name for e in g.entities)} |"
            for g in groups
        ])

        content = f"""# 情報モデル概要（ユースケース単位）

生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
ユースケース数: {len(groups)}

> ユースケース内で操作される関連エンティティを1つの「情報」としてグループ化しています。
> エンティティ単位の詳細は [情報モデル（ER図）](./information_model.md) を参照してください。

## 概要図

```mermaid
{mermaid_content}
```

## グループ一覧

| UC ID | ユースケース名 | アクター | 含まれるエンティティ |
|-------|-------------|---------|-------------------|
{group_rows}
"""
        file_path = rdra_dir / "information_model_grouped.md"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def _render_usecase_diagram(
        self, usecases: list[Usecase], rdra_dir: Path
    ) -> str:
        """ユースケース複合図のMarkdownファイルを生成する"""
        mermaid_content = self._uc_diagram_gen.generate_mermaid(usecases)

        content = f"""# ユースケース複合図

生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
ユースケース数: {len(usecases)}

## 図

```mermaid
{mermaid_content}
```

## ユースケース一覧

| ID | 名前 | アクター | カテゴリ | 優先度 |
|----|-----|---------|---------|-------|
{chr(10).join([
    f"| {uc.id} | {uc.name} | {uc.actor} | {uc.category} | {uc.priority} |"
    for uc in usecases
])}
"""
        file_path = rdra_dir / "usecase_diagram.md"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def _render_usecase_conditions(
        self, usecases: list[Usecase], rdra_dir: Path
    ) -> str:
        """ユースケース条件図のMarkdownファイルを生成する"""
        mermaid_content = self._uc_diagram_gen.generate_conditions_mermaid(usecases)

        content = f"""# ユースケース複合図（条件・バリエーション付き）

生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 図（上位20件）

```mermaid
{mermaid_content}
```

## 事前条件・事後条件詳細

"""
        for uc in usecases:
            content += f"### {uc.id}: {uc.name}\n\n"
            content += f"**アクター**: {uc.actor}  \n"
            content += f"**説明**: {uc.description}\n\n"
            if uc.preconditions:
                content += "**事前条件**:\n"
                for pre in uc.preconditions:
                    content += f"- {pre}\n"
                content += "\n"
            if uc.postconditions:
                content += "**事後条件**:\n"
                for post in uc.postconditions:
                    content += f"- {post}\n"
                content += "\n"

        file_path = rdra_dir / "usecase_conditions.md"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def _render_state_transitions(
        self,
        machines: list[EntityStateMachine],
        rdra_dir: Path,
    ) -> str:
        """状態遷移図のMarkdownファイルを生成する"""
        content = f"""# 状態遷移図

生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
対象エンティティ数: {len(machines)}

"""
        for m in machines:
            mermaid_content = self._state_gen.to_mermaid(m)
            content += f"""## {m.entity_name}（{m.entity_class}.{m.state_field}）

状態数: {len(m.states)} | 遷移数: {len(m.transitions)}

```mermaid
{mermaid_content}
```

### 状態一覧

| 状態 | 種別 |
|-----|------|
"""
            for s in m.states:
                kind = "初期状態" if s == m.initial_state else ("終了状態" if s in m.final_states else "中間状態")
                content += f"| {s} | {kind} |\n"

            content += "\n### 遷移一覧\n\n"
            content += "| 遷移元 | 遷移先 | トリガー | ガード条件 |\n"
            content += "|-------|-------|---------|----------|\n"
            for t in m.transitions:
                content += f"| {t.from_state} | {t.to_state} | {t.trigger} | {t.guard or '-'} |\n"
            content += "\n---\n\n"

        file_path = rdra_dir / "state_transitions.md"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def _render_business_policies(
        self,
        policies: list[BusinessPolicy],
        rdra_dir: Path,
    ) -> str:
        """ビジネスポリシー一覧のMarkdownファイルを生成する"""
        # カテゴリ別に整理
        categories: dict[str, list[BusinessPolicy]] = {}
        for bp in policies:
            categories.setdefault(bp.category, []).append(bp)

        severity_label = {"must": "必須", "should": "推奨", "may": "任意"}

        content = f"""# ビジネスポリシー一覧

生成日時: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
ポリシー数: {len(policies)}

## サマリ

| カテゴリ | 件数 |
|---------|-----|
"""
        for cat, bps in sorted(categories.items()):
            content += f"| {cat} | {len(bps)} |\n"

        content += "\n## 全ポリシー一覧\n\n"
        content += "| ID | 名前 | カテゴリ | 重要度 | 関連エンティティ |\n"
        content += "|----|-----|---------|-------|----------------|\n"
        for bp in policies:
            sev = severity_label.get(bp.severity, bp.severity)
            ents = ", ".join(bp.related_entities[:3])
            content += f"| {bp.id} | {bp.name} | {bp.category} | {sev} | {ents} |\n"

        content += "\n"

        for cat, bps in sorted(categories.items()):
            content += f"## {cat}\n\n"
            for bp in bps:
                sev = severity_label.get(bp.severity, bp.severity)
                content += f"### {bp.id}: {bp.name}\n\n"
                content += f"- **重要度**: {sev}\n"
                content += f"- **説明**: {bp.description}\n"
                if bp.related_entities:
                    content += f"- **関連エンティティ**: {', '.join(bp.related_entities)}\n"
                if bp.related_usecases:
                    content += f"- **関連ユースケース**: {', '.join(bp.related_usecases)}\n"
                if hasattr(bp, "code_references") and bp.code_references:
                    content += f"- **コード参照**:\n"
                    for ref in bp.code_references:
                        content += f"  - `{ref.file_path}` — {ref.description}"
                        if ref.code_type:
                            content += f" ({ref.code_type})"
                        content += "\n"
                content += "\n"

        file_path = rdra_dir / "business_policies.md"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def _render_index(
        self,
        entities: list[Entity],
        usecases: list[Usecase],
        scenarios: list[OperationScenario],
        all_files: list[str],
        rdra_dir: Path,
        state_machines: list[EntityStateMachine] = None,
        policies: list[BusinessPolicy] = None,
    ) -> str:
        """RDRAドキュメントのインデックスページを生成する"""
        project_name = self._project_name or "（未設定）"
        content = f"""# RDRA 分析結果インデックス

**プロジェクト**: {project_name}
**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 統計

| 項目 | 件数 |
|-----|-----|
| エンティティ数 | {len(entities)} |
| ユースケース数 | {len(usecases)} |
| 操作シナリオ数 | {len(scenarios)} |
| 状態遷移エンティティ数 | {len(state_machines or [])} |
| ビジネスポリシー数 | {len(policies or [])} |

## ドキュメント一覧

### 情報モデル
- [情報モデル概要（ユースケース単位）](./information_model_grouped.md)
- [情報モデル詳細（ER図）](./information_model.md)

### ユースケース
- [ユースケース複合図](./usecase_diagram.md)
- [ユースケース複合図（条件付き）](./usecase_conditions.md)

### 操作シナリオ（アクティビティ図）
- [シナリオ一覧](./activities/scenarios_overview.md)
- 個別シナリオ: activities/scenario_*.md

### 状態遷移図
"""
        if state_machines:
            content += "- [状態遷移図](./state_transitions.md)\n"
        else:
            content += "- （状態フィールドを持つエンティティが検出されませんでした）\n"

        content += """
### ビジネスポリシー
"""
        if policies:
            content += "- [ビジネスポリシー一覧](./business_policies.md)\n"
        else:
            content += "- （ビジネスポリシーが抽出されませんでした）\n"

        content += """
## カテゴリ別ユースケース

"""
        # カテゴリ別に整理
        categories: dict[str, list[Usecase]] = {}
        for uc in usecases:
            categories.setdefault(uc.category, []).append(uc)

        for category, cat_usecases in sorted(categories.items()):
            content += f"### {category}\n\n"
            for uc in cat_usecases:
                content += f"- **{uc.id}**: {uc.name} ({uc.actor})\n"
            content += "\n"

        file_path = rdra_dir / "index.md"
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)
