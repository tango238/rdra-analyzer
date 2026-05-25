"""
RequirementsGenerator のユニットテスト

RDRA2.0 の4層レイヤー構造に沿った抽出処理をテストする。
"""

import json
from unittest.mock import MagicMock

from rdra.requirements_generator import (
    RequirementsGenerator,
    RDRAGenerationResult,
    Actor, ExternalSystem, Requirement,
    Business, BusinessUseCase, BusinessFlow, UsageScene,
    Variation, Condition,
    _extract_json,
)
from rdra.information_model import Entity, Relationship
from rdra.state_transition import EntityStateMachine, StateTransition
from rdra.business_policy import BusinessPolicy
from analyzer.usecase_extractor import Usecase
from analyzer.scenario_builder import OperationScenario, OperationStep


class TestExtractJson:
    def test_plain_json(self):
        text = '{"entities": []}'
        assert _extract_json(text) == {"entities": []}

    def test_json_in_code_block(self):
        text = '```json\n{"entities": [{"name": "test"}]}\n```'
        assert _extract_json(text) == {"entities": [{"name": "test"}]}

    def test_json_with_surrounding_text(self):
        text = 'Here is the result:\n{"entities": []}\nDone.'
        assert _extract_json(text) == {"entities": []}

    def test_invalid_json_returns_none(self):
        assert _extract_json("not json at all") is None

    def test_empty_string(self):
        assert _extract_json("") is None


class TestStep1SystemValue:
    def test_parse_actors_and_requirements(self):
        response = json.dumps({
            "actors": [
                {"name": "管理者", "description": "システム管理者"}
            ],
            "external_systems": [
                {"name": "決済サービス", "description": "カード決済"}
            ],
            "requirements": [
                {"id": "REQ-001", "description": "在庫管理したい",
                 "source": "管理者", "reason": "手動管理は非効率"}
            ],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        actors, ext_sys, reqs = gen._step1_system_value("テスト要件")
        assert len(actors) == 1
        assert actors[0].name == "管理者"
        assert len(ext_sys) == 1
        assert ext_sys[0].name == "決済サービス"
        assert len(reqs) == 1
        assert reqs[0].source == "管理者"

    def test_failure_returns_empty(self):
        mock_llm = MagicMock()
        mock_llm.complete_simple.side_effect = Exception("API error")
        gen = RequirementsGenerator(mock_llm)
        actors, ext_sys, reqs = gen._step1_system_value("テスト")
        assert actors == []
        assert ext_sys == []
        assert reqs == []


class TestStep2BusinessContext:
    def test_parse_businesses_and_bucs(self):
        response = json.dumps({
            "businesses": [
                {"name": "受注業務", "actors": ["営業担当"]}
            ],
            "business_usecases": [
                {"id": "BUC-001", "name": "注文受付",
                 "business": "受注業務", "actors": ["営業担当"]}
            ],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        businesses, bucs = gen._step2_business_context(
            "テスト", [Actor(name="営業担当")], []
        )
        assert len(businesses) == 1
        assert businesses[0].name == "受注業務"
        assert len(bucs) == 1
        assert bucs[0].id == "BUC-001"


class TestStep3BusinessFlows:
    def test_parse_flows_and_scenes(self):
        response = json.dumps({
            "business_flows": [
                {"buc_id": "BUC-001", "buc_name": "注文受付",
                 "steps": [
                     {"step_no": 1, "actor": "顧客",
                      "action": "商品を選択", "next_step": ""}
                 ]}
            ],
            "usage_scenes": [
                {"buc_id": "BUC-002", "buc_name": "商品検索",
                 "scene_name": "キーワード検索",
                 "description": "キーワードで商品を探す",
                 "steps": [
                     {"step_no": 1, "actor": "顧客",
                      "action": "検索する", "next_step": ""}
                 ]}
            ],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        flows, scenes = gen._step3_business_flows(
            "テスト", [BusinessUseCase(id="BUC-001", name="注文受付", business="受注")]
        )
        assert len(flows) == 1
        assert len(flows[0].steps) == 1
        assert len(scenes) == 1
        assert scenes[0].scene_name == "キーワード検索"


class TestStep4Variations:
    def test_parse_variations_and_conditions(self):
        response = json.dumps({
            "variations": [
                {"name": "会員種別", "values": ["一般", "プレミアム"]}
            ],
            "conditions": [
                {"name": "送料無料条件",
                 "variations": ["会員種別"],
                 "description": "プレミアム会員は送料無料"}
            ],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        variations, conditions = gen._step4_variations("テスト", [], [])
        assert len(variations) == 1
        assert variations[0].values == ["一般", "プレミアム"]
        assert len(conditions) == 1
        assert conditions[0].name == "送料無料条件"


class TestStep5UCComposite:
    def test_parse_usecases(self):
        response = json.dumps({
            "usecases": [
                {"id": "UC-001", "name": "商品注文",
                 "actor": "顧客", "description": "注文する",
                 "preconditions": ["ログイン済み"],
                 "postconditions": ["注文確定"],
                 "related_entities": ["注文"],
                 "category": "受注業務", "priority": "high"}
            ]
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        usecases = gen._parse_usecases_response(response)
        assert len(usecases) == 1
        assert usecases[0].id == "UC-001"
        assert usecases[0].related_routes == []


class TestStep6InformationModel:
    def test_parse_entities(self):
        response = json.dumps({
            "entities": [
                {"name": "注文", "class_name": "Order",
                 "table_name": "orders",
                 "attributes": ["注文番号", "合計金額"],
                 "description": "顧客の注文"}
            ],
            "relationships": [
                {"from_entity": "顧客", "to_entity": "注文",
                 "relation_type": "1-N", "label": "注文する"}
            ],
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        entities, rels = gen._parse_entities_response(response)
        assert len(entities) == 1
        assert entities[0].class_name == "Order"
        assert len(rels) == 1


class TestStep7StateModel:
    def test_parse_state_machines(self):
        response = json.dumps({
            "state_machines": [
                {"entity_name": "注文", "entity_class": "Order",
                 "state_field": "status",
                 "states": ["下書き", "確定"],
                 "transitions": [
                     {"from_state": "下書き", "to_state": "確定",
                      "trigger": "注文確定", "guard": ""}
                 ],
                 "initial_state": "下書き",
                 "final_states": ["確定"]}
            ]
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        machines = gen._parse_state_machines_response(response)
        assert len(machines) == 1
        assert machines[0].entity_class == "Order"


class TestStep8BusinessRules:
    def test_parse_policies(self):
        response = json.dumps({
            "policies": [
                {"id": "BP-001", "name": "送料無料",
                 "category": "計算",
                 "description": "プレミアム会員は送料無料",
                 "related_entities": ["注文"],
                 "related_usecases": ["UC-001"],
                 "severity": "must"}
            ]
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        policies = gen._parse_policies_response(response)
        assert len(policies) == 1
        assert policies[0].id == "BP-001"


class TestFullOrchestration:
    def test_generate_calls_all_8_steps(self):
        """RDRA2.0の8ステップが全て呼ばれることを確認"""
        mock_llm = MagicMock()

        step1_resp = json.dumps({
            "actors": [{"name": "管理者", "description": ""}],
            "external_systems": [],
            "requirements": [
                {"id": "REQ-001", "description": "商品管理",
                 "source": "管理者", "reason": "効率化"}],
        }, ensure_ascii=False)

        step2_resp = json.dumps({
            "businesses": [{"name": "商品管理業務", "actors": ["管理者"]}],
            "business_usecases": [
                {"id": "BUC-001", "name": "商品登録",
                 "business": "商品管理業務", "actors": ["管理者"]}],
        }, ensure_ascii=False)

        step3_resp = json.dumps({
            "business_flows": [
                {"buc_id": "BUC-001", "buc_name": "商品登録",
                 "steps": [{"step_no": 1, "actor": "管理者",
                            "action": "登録画面を開く", "next_step": ""}]}],
            "usage_scenes": [],
        }, ensure_ascii=False)

        step4_resp = json.dumps({
            "variations": [],
            "conditions": [],
        }, ensure_ascii=False)

        step5_resp = json.dumps({
            "usecases": [
                {"id": "UC-001", "name": "商品登録", "actor": "管理者",
                 "description": "新商品を登録", "preconditions": [],
                 "postconditions": [], "related_entities": ["商品"],
                 "category": "商品管理業務", "priority": "high"}],
        }, ensure_ascii=False)

        step6_resp = json.dumps({
            "entities": [
                {"name": "商品", "class_name": "Product",
                 "table_name": "products",
                 "attributes": ["名前", "価格"],
                 "description": "販売商品"}],
            "relationships": [],
        }, ensure_ascii=False)

        step7_resp = json.dumps({"state_machines": []}, ensure_ascii=False)
        step8_resp = json.dumps({"policies": []}, ensure_ascii=False)

        mock_llm.complete_simple.side_effect = [
            step1_resp, step2_resp, step3_resp, step4_resp,
            step5_resp, step6_resp, step7_resp, step8_resp,
        ]

        gen = RequirementsGenerator(mock_llm)
        result = gen.generate("ECサイトの要件定義")

        assert isinstance(result, RDRAGenerationResult)
        # Layer 1
        assert len(result.actors) == 1
        assert len(result.requirements) == 1
        # Layer 2
        assert len(result.businesses) == 1
        assert len(result.business_usecases) == 1
        assert len(result.business_flows) == 1
        # Layer 3
        assert len(result.usecases) == 1
        # Layer 4
        assert len(result.entities) == 1
        # 8回のLLM呼び出し
        assert mock_llm.complete_simple.call_count == 8


class TestDeriveScenarios:
    def test_scenarios_derived_from_flows(self):
        mock_llm = MagicMock()
        gen = RequirementsGenerator(mock_llm)

        from rdra.requirements_generator import ActivityStep
        usecases = [
            Usecase(id="UC-001", name="注文", actor="顧客",
                    description="", preconditions=[], postconditions=[],
                    related_routes=[], related_pages=[],
                    related_entities=[], category="受注業務")
        ]
        flows = [
            BusinessFlow(
                buc_id="BUC-001", buc_name="注文受付",
                steps=[
                    ActivityStep(step_no=1, actor="顧客", action="商品選択"),
                    ActivityStep(step_no=2, actor="システム", action="注文確定"),
                ],
            )
        ]
        scenarios = gen._derive_scenarios(usecases, flows, [])
        assert len(scenarios) >= 1
        assert scenarios[0].usecase_id == "UC-001"
        assert len(scenarios[0].steps) == 2
