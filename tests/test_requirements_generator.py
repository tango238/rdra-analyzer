"""
RequirementsGenerator のユニットテスト

LLMレスポンスのパース処理を中心にテストする。
"""

import json
from unittest.mock import MagicMock

from rdra.requirements_generator import (
    RequirementsGenerator,
    RDRAGenerationResult,
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


class TestParseEntities:
    def _make_generator(self, response_text: str) -> RequirementsGenerator:
        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response_text
        return RequirementsGenerator(mock_llm)

    def test_parse_entities_basic(self):
        response = json.dumps({
            "entities": [
                {
                    "name": "ユーザー",
                    "class_name": "User",
                    "table_name": "users",
                    "attributes": ["名前", "メールアドレス"],
                    "description": "システム利用者",
                }
            ],
            "relationships": [
                {
                    "from_entity": "ユーザー",
                    "to_entity": "注文",
                    "relation_type": "1-N",
                    "label": "注文する",
                }
            ],
        }, ensure_ascii=False)

        gen = self._make_generator(response)
        entities, rels = gen._extract_entities("テスト要件")
        assert len(entities) == 1
        assert entities[0].name == "ユーザー"
        assert entities[0].class_name == "User"
        assert len(rels) == 1
        assert rels[0].relation_type == "1-N"

    def test_parse_entities_empty(self):
        gen = self._make_generator('{"entities": [], "relationships": []}')
        entities, rels = gen._extract_entities("テスト")
        assert entities == []
        assert rels == []


class TestParseUsecases:
    def _make_generator(self, response_text: str) -> RequirementsGenerator:
        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response_text
        return RequirementsGenerator(mock_llm)

    def test_parse_usecases_basic(self):
        response = json.dumps({
            "usecases": [
                {
                    "id": "UC-001",
                    "name": "ユーザー登録",
                    "actor": "未登録ユーザー",
                    "description": "新規登録する",
                    "preconditions": ["未登録であること"],
                    "postconditions": ["アカウントが作成される"],
                    "related_entities": ["ユーザー"],
                    "category": "ユーザー管理",
                    "priority": "high",
                }
            ]
        }, ensure_ascii=False)

        gen = self._make_generator(response)
        usecases = gen._parse_usecases_response(response)
        assert len(usecases) == 1
        assert usecases[0].id == "UC-001"
        assert usecases[0].actor == "未登録ユーザー"
        assert usecases[0].priority == "high"
        assert usecases[0].related_routes == []


class TestParseScenarios:
    def _make_generator(self, response_text: str) -> RequirementsGenerator:
        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response_text
        return RequirementsGenerator(mock_llm)

    def test_parse_scenarios_basic(self):
        response = json.dumps({
            "scenarios": [
                {
                    "usecase_id": "UC-001",
                    "usecase_name": "ユーザー登録",
                    "scenario_id": "SC-001-01",
                    "scenario_name": "正常系",
                    "scenario_type": "normal",
                    "steps": [
                        {
                            "step_no": 1,
                            "actor": "ユーザー",
                            "action": "登録画面を開く",
                            "expected_result": "フォームが表示される",
                        },
                        {
                            "step_no": 2,
                            "actor": "システム",
                            "action": "アカウントを作成",
                            "expected_result": "完了画面が表示される",
                        },
                    ],
                    "variations": ["SNS登録"],
                }
            ]
        }, ensure_ascii=False)

        gen = self._make_generator(response)
        scenarios = gen._parse_scenarios_response(response)
        assert len(scenarios) == 1
        assert scenarios[0].scenario_id == "SC-001-01"
        assert len(scenarios[0].steps) == 2
        assert scenarios[0].steps[0].actor == "ユーザー"
        assert scenarios[0].variations == ["SNS登録"]


class TestParseStateMachines:
    def test_parse_state_machines_basic(self):
        response = json.dumps({
            "state_machines": [
                {
                    "entity_name": "注文",
                    "entity_class": "Order",
                    "state_field": "status",
                    "states": ["下書き", "確定", "出荷済み"],
                    "transitions": [
                        {
                            "from_state": "下書き",
                            "to_state": "確定",
                            "trigger": "注文確定",
                            "guard": "在庫あり",
                        }
                    ],
                    "initial_state": "下書き",
                    "final_states": ["出荷済み"],
                }
            ]
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        machines = gen._parse_state_machines_response(response)
        assert len(machines) == 1
        assert machines[0].entity_class == "Order"
        assert len(machines[0].transitions) == 1
        assert machines[0].transitions[0].trigger == "注文確定"
        assert machines[0].initial_state == "下書き"


class TestParsePolicies:
    def test_parse_policies_basic(self):
        response = json.dumps({
            "policies": [
                {
                    "id": "BP-001",
                    "name": "メールアドレス一意性",
                    "category": "制約",
                    "description": "重複登録を禁止",
                    "related_entities": ["ユーザー"],
                    "related_usecases": ["UC-001"],
                    "severity": "must",
                }
            ]
        }, ensure_ascii=False)

        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response
        gen = RequirementsGenerator(mock_llm)

        policies = gen._parse_policies_response(response)
        assert len(policies) == 1
        assert policies[0].id == "BP-001"
        assert policies[0].severity == "must"


class TestGenerateOrchestration:
    def test_generate_calls_all_phases(self):
        mock_llm = MagicMock()

        entities_resp = json.dumps({
            "entities": [
                {"name": "商品", "class_name": "Product", "table_name": "products",
                 "attributes": ["名前", "価格"], "description": "販売商品"}
            ],
            "relationships": [],
        }, ensure_ascii=False)

        usecases_resp = json.dumps({
            "usecases": [
                {"id": "UC-001", "name": "商品登録", "actor": "管理者",
                 "description": "新商品を登録", "preconditions": [],
                 "postconditions": [], "related_entities": ["商品"],
                 "category": "商品管理", "priority": "high"}
            ]
        }, ensure_ascii=False)

        scenarios_resp = json.dumps({
            "scenarios": [
                {"usecase_id": "UC-001", "usecase_name": "商品登録",
                 "scenario_id": "SC-001-01", "scenario_name": "正常系",
                 "scenario_type": "normal",
                 "steps": [
                     {"step_no": 1, "actor": "管理者", "action": "登録画面を開く",
                      "expected_result": "フォーム表示"}
                 ],
                 "variations": []}
            ]
        }, ensure_ascii=False)

        states_resp = json.dumps({"state_machines": []}, ensure_ascii=False)
        policies_resp = json.dumps({"policies": []}, ensure_ascii=False)

        mock_llm.complete_simple.side_effect = [
            entities_resp, usecases_resp, scenarios_resp,
            states_resp, policies_resp,
        ]

        gen = RequirementsGenerator(mock_llm)
        result = gen.generate("ECサイトの要件定義")

        assert isinstance(result, RDRAGenerationResult)
        assert len(result.entities) == 1
        assert len(result.usecases) == 1
        assert len(result.scenarios) == 1
        assert mock_llm.complete_simple.call_count == 5


class TestLLMFailure:
    def test_entity_extraction_failure_returns_empty(self):
        mock_llm = MagicMock()
        mock_llm.complete_simple.side_effect = Exception("API error")
        gen = RequirementsGenerator(mock_llm)

        entities, rels = gen._extract_entities("テスト")
        assert entities == []
        assert rels == []

    def test_usecase_extraction_failure_returns_empty(self):
        mock_llm = MagicMock()
        mock_llm.complete_simple.side_effect = Exception("API error")
        gen = RequirementsGenerator(mock_llm)

        usecases = gen._extract_usecases("テスト", [])
        assert usecases == []
