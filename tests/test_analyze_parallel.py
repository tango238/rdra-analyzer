"""リポジトリ並列解析ヘルパーの単体テスト"""
from analyzer.source_parser import RepoParseResult


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
