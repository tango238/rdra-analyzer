"""
TestCodeGenerator のユニットテスト
"""

import json
from unittest.mock import MagicMock
from pathlib import Path
import tempfile

from e2e.test_generator import (
    TestCodeGenerator,
    GeneratedTest,
    save_generated_tests,
    _language_extension,
)
from analyzer.source_parser import ParsedRoute, ParsedController, ParsedModel


class TestParseResponse:
    def _make_generator(self, response_text: str) -> TestCodeGenerator:
        mock_llm = MagicMock()
        mock_llm.complete_simple.return_value = response_text
        return TestCodeGenerator(mock_llm)

    def test_parse_valid_response(self):
        response = json.dumps({
            "file_path": "tests/Feature/OrderTest.php",
            "language": "PHP",
            "test_framework": "PHPUnit",
            "description": "注文テスト",
            "code": "<?php\nclass OrderTest {}\n",
        }, ensure_ascii=False)

        gen = self._make_generator(response)
        result = gen._parse_test_response(
            response, source_id="BUC-001",
            source_name="注文受付", source_type="business_flow",
        )
        assert result is not None
        assert result.file_path == "tests/Feature/OrderTest.php"
        assert result.language == "PHP"
        assert result.code.startswith("<?php")

    def test_parse_empty_code_returns_none(self):
        response = json.dumps({
            "file_path": "test.py",
            "language": "Python",
            "test_framework": "pytest",
            "code": "",
        }, ensure_ascii=False)

        gen = self._make_generator(response)
        result = gen._parse_test_response(
            response, source_id="BUC-001",
            source_name="テスト", source_type="business_flow",
        )
        assert result is None

    def test_parse_invalid_json_returns_none(self):
        gen = self._make_generator("invalid")
        result = gen._parse_test_response(
            "not json", source_id="BUC-001",
            source_name="テスト", source_type="business_flow",
        )
        assert result is None


class TestGenerateFromFlows:
    def test_generate_calls_llm_for_each_flow_and_scene(self):
        mock_llm = MagicMock()

        flow_resp = json.dumps({
            "file_path": "tests/test_order.py",
            "language": "Python",
            "test_framework": "pytest",
            "description": "注文テスト",
            "code": "def test_order(): pass",
        }, ensure_ascii=False)

        scene_resp = json.dumps({
            "file_path": "tests/test_search.py",
            "language": "Python",
            "test_framework": "pytest",
            "description": "検索テスト",
            "code": "def test_search(): pass",
        }, ensure_ascii=False)

        mock_llm.complete_simple.side_effect = [flow_resp, scene_resp]

        gen = TestCodeGenerator(mock_llm)
        tests = gen.generate_from_flows(
            business_flows=[
                {"buc_id": "BUC-001", "buc_name": "注文受付",
                 "steps": [{"step_no": 1, "actor": "顧客", "action": "注文する"}]}
            ],
            usage_scenes=[
                {"buc_id": "BUC-002", "buc_name": "商品検索",
                 "scene_name": "キーワード検索",
                 "description": "検索する",
                 "steps": [{"step_no": 1, "actor": "顧客", "action": "検索する"}]}
            ],
            routes=[],
            controllers=[],
            models=[],
            project_context="",
            tech_stack="Python / FastAPI",
        )

        assert len(tests) == 2
        assert tests[0].source_type == "business_flow"
        assert tests[1].source_type == "usage_scene"
        assert mock_llm.complete_simple.call_count == 2

    def test_llm_failure_skips_test(self):
        mock_llm = MagicMock()
        mock_llm.complete_simple.side_effect = Exception("API error")

        gen = TestCodeGenerator(mock_llm)
        tests = gen.generate_from_flows(
            business_flows=[
                {"buc_id": "BUC-001", "buc_name": "テスト",
                 "steps": []}
            ],
            usage_scenes=[],
            routes=[], controllers=[], models=[],
            project_context="", tech_stack="",
        )
        assert tests == []


class TestSaveGeneratedTests:
    def test_save_creates_files(self):
        tests = [
            GeneratedTest(
                source_id="BUC-001", source_name="注文受付",
                source_type="business_flow",
                file_path="tests/test_order.py",
                language="Python", test_framework="pytest",
                code="def test_order(): pass",
                description="注文テスト",
            )
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_generated_tests(tests, Path(tmpdir))
            assert len(saved) == 2  # test file + README.md
            assert any("test_order.py" in s for s in saved)
            assert any("README.md" in s for s in saved)


class TestBuildSummaries:
    def test_route_summary(self):
        gen = TestCodeGenerator(MagicMock())
        routes = [
            ParsedRoute(method="GET", path="/api/orders", controller="OrderController",
                        action="index", middleware=["auth"]),
        ]
        summary = gen._build_route_summary(routes)
        assert "GET" in summary
        assert "/api/orders" in summary

    def test_empty_routes(self):
        gen = TestCodeGenerator(MagicMock())
        assert gen._build_route_summary([]) == "(なし)"


class TestLanguageExtension:
    def test_known_languages(self):
        assert _language_extension("PHP") == ".php"
        assert _language_extension("python") == ".py"
        assert _language_extension("TypeScript") == ".ts"

    def test_unknown_language(self):
        assert _language_extension("unknown") == ".txt"
