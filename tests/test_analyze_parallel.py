"""リポジトリ並列解析ヘルパーの単体テスト"""
from unittest.mock import MagicMock

import pytest
import typer

from analyzer.source_parser import RepoParseResult
from main import _parse_single_repo, _resolve_parallel


class TestRepoParseResult:
    def test_success_result_has_empty_lists_by_default(self):
        result = RepoParseResult(repo_name="r1", success=True)
        assert result.repo_name == "r1"
        assert result.success is True
        assert result.routes == []
        assert result.controllers == []
        assert result.models == []
        assert result.pages == []
        assert result.entity_operations == []
        assert result.error is None

    def test_failure_result_carries_error_message(self):
        result = RepoParseResult(
            repo_name="bad", success=False, error="LLM timeout"
        )
        assert result.success is False
        assert result.error == "LLM timeout"
        assert result.routes == []

    def test_default_lists_are_independent_between_instances(self):
        """field(default_factory=list) が正しく使われていることの検証"""
        a = RepoParseResult(repo_name="a", success=True)
        b = RepoParseResult(repo_name="b", success=True)
        a.routes.append("x")
        assert b.routes == []


class TestResolveParallel:
    def test_zero_with_two_repos_returns_two(self):
        assert _resolve_parallel(0, 2) == 2

    def test_zero_with_many_repos_caps_at_four(self):
        assert _resolve_parallel(0, 10) == 4

    def test_zero_with_one_repo_returns_one(self):
        assert _resolve_parallel(0, 1) == 1

    def test_explicit_one_returns_one(self):
        assert _resolve_parallel(1, 5) == 1

    def test_explicit_exceeds_repos_preserved(self):
        assert _resolve_parallel(8, 3) == 8

    def test_negative_raises_bad_parameter(self):
        with pytest.raises(typer.BadParameter):
            _resolve_parallel(-1, 5)

    def test_zero_with_empty_returns_one(self):
        assert _resolve_parallel(0, 0) == 1


class TestParseSingleRepo:
    def test_success_returns_populated_result(self, tmp_path):
        repo = tmp_path / "repo1"
        repo.mkdir()
        parser = MagicMock()
        parser.parse_repo.return_value = {
            "routes": ["r1", "r2"],
            "controllers": ["c1"],
            "models": ["m1"],
            "pages": [],
            "entity_operations": ["eo1"],
        }

        result = _parse_single_repo(repo, parser)

        assert result.success is True
        assert result.repo_name == "repo1"
        assert result.routes == ["r1", "r2"]
        assert result.controllers == ["c1"]
        assert result.models == ["m1"]
        assert result.pages == []
        assert result.entity_operations == ["eo1"]
        assert result.error is None
        parser.parse_repo.assert_called_once_with(repo)

    def test_failure_captures_exception_message(self, tmp_path):
        repo = tmp_path / "bad"
        repo.mkdir()
        parser = MagicMock()
        parser.parse_repo.side_effect = RuntimeError("LLM timeout after 120s")

        result = _parse_single_repo(repo, parser)

        assert result.success is False
        assert result.repo_name == "bad"
        assert result.error == "LLM timeout after 120s"
        assert result.routes == []
        assert result.models == []

    def test_missing_entity_operations_defaults_to_empty(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        parser = MagicMock()
        parser.parse_repo.return_value = {
            "routes": [],
            "controllers": [],
            "models": [],
            "pages": [],
        }

        result = _parse_single_repo(repo, parser)

        assert result.success is True
        assert result.entity_operations == []
