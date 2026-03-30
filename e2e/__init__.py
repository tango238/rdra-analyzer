"""
パート4: E2Eテスト実行パッケージ

Playwright で操作シナリオを自動実行する。
エラー発生時はエージェントループで原因判断・リカバリーを行う。
"""

from .playwright_runner import PlaywrightRunner
from .agent_loop import AgentLoop, AgentState
from .scenario_executor import ScenarioExecutor

__all__ = [
    "PlaywrightRunner",
    "AgentLoop",
    "AgentState",
    "ScenarioExecutor",
]
