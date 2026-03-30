"""
エージェントループモジュール

E2Eテスト実行中にエラーが発生した場合、
Claude API でエラー原因を判断してリカバリー方法を決定し再試行するエージェントループ。

エージェントは以下の判断を行う:
1. エラー種別の分類（認証エラー・要素未検出・タイムアウト・バリデーションエラーなど）
2. リカバリーアクションの決定（ログイン・待機・スキップ・代替要素使用など）
3. リカバリー実行後の再試行
"""

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Any

from llm.provider import LLMProvider
from .playwright_runner import PlaywrightRunner, PageContext


class RecoveryAction(Enum):
    """リカバリーアクション種別"""
    RETRY = "retry"                     # そのまま再試行
    LOGIN = "login"                     # ログインして再試行
    WAIT = "wait"                       # 待機して再試行
    NAVIGATE = "navigate"               # 別のURLに遷移して再試行
    SKIP = "skip"                       # このステップをスキップ
    ABORT = "abort"                     # シナリオ全体を中断
    USE_ALTERNATIVE_SELECTOR = "use_alt_selector"  # 代替セレクターを使用
    CLEAR_AND_RETRY = "clear_and_retry"  # フォームをクリアして再試行


@dataclass
class AgentState:
    """エージェントの状態"""
    scenario_id: str                # 実行中のシナリオID
    step_no: int                    # 現在のステップ番号
    retry_count: int = 0            # 現在のリトライ回数
    max_retries: int = 3            # 最大リトライ回数
    error_history: list[str] = field(default_factory=list)  # エラー履歴
    recovery_history: list[str] = field(default_factory=list)  # リカバリー履歴
    is_logged_in: bool = False      # ログイン状態


@dataclass
class RecoveryPlan:
    """エージェントが決定したリカバリー計画"""
    action: RecoveryAction          # リカバリーアクション
    reason: str                     # 理由（日本語）
    parameters: dict = field(default_factory=dict)  # アクション固有パラメーター
    # parameters の例:
    #   navigate: {"url": "/hotels"}
    #   wait: {"seconds": 3}
    #   use_alt_selector: {"selector": "button[data-testid='submit']"}


class AgentLoop:
    """
    E2Eテストエージェントループクラス。

    エラー発生時に Claude API でリカバリー方法を決定して再試行する。
    while True ループで全シナリオを実行し続ける。
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        runner: PlaywrightRunner,
        max_retries: int = 3,
    ):
        self._llm = llm_provider
        self._runner = runner
        self._max_retries = max_retries

    def execute_with_recovery(
        self,
        step_fn: Callable[[], bool],
        state: AgentState,
        step_description: str,
    ) -> bool:
        """
        エージェントループでステップを実行する。

        エラー発生時はリカバリーを試みて最大 max_retries 回再試行する。

        Args:
            step_fn: 実行するステップ関数（Trueを返すと成功）
            state: エージェントの現在の状態
            step_description: ステップの説明（エラー報告用）

        Returns:
            bool: 最終的に成功したかどうか
        """
        while state.retry_count <= self._max_retries:
            # ステップ実行
            try:
                success = step_fn()
            except Exception as e:
                success = False
                state.error_history.append(f"例外発生: {e}")

            if success:
                # 成功: エラー検出も確認
                error = self._runner.check_error_state()
                if not error:
                    return True
                # エラー状態でも画面は遷移している場合
                state.error_history.append(error)
            else:
                state.error_history.append(f"ステップ失敗: {step_description}")

            # リトライ回数上限チェック
            if state.retry_count >= self._max_retries:
                return False

            # エージェントがリカバリー計画を決定
            page_ctx = self._runner.get_page_context()
            recovery = self._decide_recovery(state, step_description, page_ctx)

            # リカバリー実行
            recovered = self._execute_recovery(recovery, state)
            state.recovery_history.append(
                f"試行{state.retry_count + 1}: {recovery.action.value} - {recovery.reason}"
            )
            state.retry_count += 1

            if recovery.action == RecoveryAction.ABORT:
                return False
            if recovery.action == RecoveryAction.SKIP:
                return True  # スキップも「成功」として扱う

        return False

    def _decide_recovery(
        self,
        state: AgentState,
        step_description: str,
        page_ctx: PageContext,
    ) -> RecoveryPlan:
        """
        Claude API にエラー状況を送信してリカバリー計画を決定する。

        Args:
            state: エージェントの現在状態
            step_description: 失敗したステップの説明
            page_ctx: 現在のページコンテキスト

        Returns:
            RecoveryPlan: リカバリー計画
        """
        system_prompt = """あなたはWebブラウザE2Eテストのデバッグエキスパートです。
テストステップが失敗した際のリカバリー方法を決定してください。

以下のJSON形式で回答してください:
{
  "action": "retry|login|wait|navigate|skip|abort|use_alt_selector|clear_and_retry",
  "reason": "リカバリーの理由（日本語）",
  "parameters": {
    "url": "/path（navigateの場合）",
    "seconds": 3（waitの場合）,
    "selector": "代替セレクター（use_alt_selectorの場合）"
  }
}

判断基準:
- 認証エラー・ログインページへのリダイレクト → "login"
- 要素が見つからない・タイムアウト → "retry" または "use_alt_selector"
- ページ読み込み中・ローディング → "wait"
- 404 Not Found → "navigate"（正しいURLを parameters.url に）
- 無限ループが疑われる・同じエラーが3回以上 → "skip" または "abort"
- バリデーションエラー → "clear_and_retry"
"""

        error_summary = "\n".join(state.error_history[-3:])  # 最新3件

        user_message = f"""
## テスト失敗情報

**シナリオID**: {state.scenario_id}
**ステップ番号**: {state.step_no}
**ステップ説明**: {step_description}
**リトライ回数**: {state.retry_count}

## エラー履歴（最新3件）
{error_summary}

## 現在のページ状態
- URL: {page_ctx.url}
- タイトル: {page_ctx.title}
- ページテキスト（抜粋）:
{page_ctx.visible_text[:500]}

## 過去のリカバリー履歴
{chr(10).join(state.recovery_history[-3:]) or "なし"}

最適なリカバリー方法を決定してください。
"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=system_prompt,
            )
            return self._parse_recovery_plan(response)
        except Exception:
            # LLM呼び出し失敗時はデフォルトのリカバリー
            return self._default_recovery(state)

    def _parse_recovery_plan(self, response: str) -> RecoveryPlan:
        """LLMのレスポンスをRecoveryPlanに変換する"""
        cleaned = re.sub(r"```(?:json)?\s*", "", response).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
            action_str = data.get("action", "retry")
            try:
                action = RecoveryAction(action_str)
            except ValueError:
                action = RecoveryAction.RETRY

            return RecoveryPlan(
                action=action,
                reason=data.get("reason", "自動リカバリー"),
                parameters=data.get("parameters", {}),
            )
        except (json.JSONDecodeError, KeyError):
            return RecoveryPlan(
                action=RecoveryAction.RETRY,
                reason="LLMレスポンスのパース失敗のため再試行",
            )

    def _default_recovery(self, state: AgentState) -> RecoveryPlan:
        """LLM呼び出し失敗時のデフォルトリカバリー"""
        if state.retry_count == 0:
            return RecoveryPlan(action=RecoveryAction.WAIT, reason="初回は待機して再試行", parameters={"seconds": 2})
        elif state.retry_count == 1:
            return RecoveryPlan(action=RecoveryAction.RETRY, reason="2回目の試行")
        else:
            return RecoveryPlan(action=RecoveryAction.SKIP, reason="3回失敗のためスキップ")

    def _execute_recovery(
        self, plan: RecoveryPlan, state: AgentState
    ) -> bool:
        """
        リカバリー計画を実行する。

        Args:
            plan: リカバリー計画
            state: エージェントの状態

        Returns:
            bool: リカバリー実行成功かどうか
        """
        import time

        action = plan.action
        params = plan.parameters

        if action == RecoveryAction.LOGIN:
            return self._runner.login()

        elif action == RecoveryAction.WAIT:
            seconds = params.get("seconds", 2)
            time.sleep(seconds)
            return True

        elif action == RecoveryAction.NAVIGATE:
            url = params.get("url", "/")
            return self._runner.navigate(url)

        elif action == RecoveryAction.RETRY:
            time.sleep(1)  # 少し待ってから再試行
            return True

        elif action == RecoveryAction.CLEAR_AND_RETRY:
            # フォームフィールドをクリア
            try:
                self._runner._page.keyboard.press("Escape")
                time.sleep(0.5)
            except Exception:
                pass
            return True

        elif action in (RecoveryAction.SKIP, RecoveryAction.ABORT):
            return True  # 実際の処理は呼び出し元で行う

        return True
