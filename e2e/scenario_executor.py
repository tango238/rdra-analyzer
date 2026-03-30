"""
シナリオ実行管理モジュール

操作シナリオを Playwright で自動実行し、
エラー時はエージェントループでリカバリーを試みる。

while True ループで全シナリオを途切れなく実行し続ける。
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn

from llm.provider import LLMProvider
from analyzer.scenario_builder import OperationScenario, OperationStep
from config import get_config
from .playwright_runner import PlaywrightRunner
from .agent_loop import AgentLoop, AgentState, RecoveryAction


@dataclass
class ScenarioResult:
    """シナリオ実行結果"""
    scenario_id: str            # シナリオID
    scenario_name: str          # シナリオ名
    usecase_id: str             # ユースケースID
    status: str                 # "success" | "failed" | "skipped"
    steps_total: int            # 総ステップ数
    steps_passed: int           # 成功ステップ数
    steps_failed: int           # 失敗ステップ数
    retry_count: int            # リトライ総数
    error_messages: list[str]   # エラーメッセージ一覧
    recovery_actions: list[str] # 実行したリカバリーアクション
    duration_seconds: float     # 実行時間（秒）
    screenshot_paths: list[str] = field(default_factory=list)  # スクリーンショットパス
    started_at: str = ""        # 開始日時
    finished_at: str = ""       # 終了日時


class ScenarioExecutor:
    """
    操作シナリオを実行するクラス。

    機能:
    - 全シナリオを while True ループで実行
    - エラー時のエージェントループによるリカバリー
    - 実行結果のJSON・Markdown保存
    - リッチなコンソール出力（進捗・結果テーブル）

    実行フロー:
    1. ログイン
    2. 各シナリオのステップを順に実行
    3. エラー時はエージェントループでリカバリー
    4. 全シナリオ完了後に結果を保存
    """

    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider
        self._config = get_config()
        self._console = Console()
        self._results: list[ScenarioResult] = []

    def run_all(
        self,
        scenarios: list[OperationScenario],
        output_dir: Optional[Path] = None,
    ) -> list[ScenarioResult]:
        """
        全シナリオを while True ループで実行する。

        while True ループで実行するため、シナリオが途切れることなく
        最後まで実行される。エラーが発生しても次のシナリオに進む。

        Args:
            scenarios: 実行する操作シナリオ一覧
            output_dir: 結果出力ディレクトリ

        Returns:
            list[ScenarioResult]: 全シナリオの実行結果
        """
        if not scenarios:
            self._console.print("[yellow]実行するシナリオがありません[/yellow]")
            return []

        output_dir = output_dir or Path(self._config.output_dir) / "e2e"
        output_dir.mkdir(parents=True, exist_ok=True)

        self._console.print(
            f"\n[bold blue]🚀 E2Eテスト開始[/bold blue]\n"
            f"シナリオ数: {len(scenarios)}\n"
            f"ベースURL: {self._config.e2e_base_url}\n"
        )

        with PlaywrightRunner() as runner:
            agent = AgentLoop(self._llm, runner, self._config.e2e_max_retries)

            # ログイン
            self._console.print("[dim]ログイン中...[/dim]")
            if not runner.login():
                self._console.print("[red]ログインに失敗しました。E2Eテストを中断します。[/red]")
                return []
            self._console.print("[green]✓ ログイン成功[/green]\n")

            # while True ループで全シナリオを実行
            scenario_idx = 0
            while True:
                # 全シナリオ完了チェック
                if scenario_idx >= len(scenarios):
                    break

                scenario = scenarios[scenario_idx]
                self._console.print(
                    f"[bold]▶ {scenario.scenario_id}: {scenario.scenario_name}[/bold] "
                    f"({scenario_idx + 1}/{len(scenarios)})"
                )

                result = self._run_scenario(scenario, runner, agent, output_dir)
                self._results.append(result)

                # 結果表示
                status_icon = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(
                    result.status, "?"
                )
                self._console.print(
                    f"  {status_icon} {result.status.upper()} "
                    f"[dim]({result.duration_seconds:.1f}s, "
                    f"ステップ {result.steps_passed}/{result.steps_total})[/dim]"
                )

                if result.error_messages:
                    for err in result.error_messages[:2]:
                        self._console.print(f"  [red]  → {err}[/red]")

                scenario_idx += 1

                # シナリオ間の待機（レート制限対策）
                time.sleep(0.5)

        # 結果を保存
        self._save_results(output_dir)

        # サマリー表示
        self._print_summary()

        return self._results

    def _run_scenario(
        self,
        scenario: OperationScenario,
        runner: PlaywrightRunner,
        agent: AgentLoop,
        output_dir: Path,
    ) -> ScenarioResult:
        """
        1シナリオを実行する。

        Args:
            scenario: 実行する操作シナリオ
            runner: Playwright ランナー
            agent: エージェントループ

        Returns:
            ScenarioResult: 実行結果
        """
        start_time = time.time()
        started_at = datetime.now().isoformat()

        result = ScenarioResult(
            scenario_id=scenario.scenario_id,
            scenario_name=scenario.scenario_name,
            usecase_id=scenario.usecase_id,
            status="success",
            steps_total=len(scenario.steps),
            steps_passed=0,
            steps_failed=0,
            retry_count=0,
            error_messages=[],
            recovery_actions=[],
            duration_seconds=0,
            started_at=started_at,
        )

        # フロントエンドURLに遷移
        if scenario.frontend_url:
            runner.navigate(scenario.frontend_url, step_no=0)

        # エージェント状態初期化
        state = AgentState(
            scenario_id=scenario.scenario_id,
            step_no=0,
            max_retries=self._config.e2e_max_retries,
        )

        # 各ステップを実行
        for step in scenario.steps:
            state.step_no = step.step_no
            state.retry_count = 0

            step_success = agent.execute_with_recovery(
                step_fn=lambda s=step, r=runner: self._execute_step(s, r),
                state=state,
                step_description=step.action,
            )

            if step_success:
                result.steps_passed += 1
            else:
                result.steps_failed += 1
                result.error_messages.extend(state.error_history[-2:])
                result.recovery_actions.extend(state.recovery_history)

        # スクリーンショット保存
        screenshot_path = runner.take_screenshot(
            f"{scenario.scenario_id}_final",
            step_no=len(scenario.steps)
        )
        if screenshot_path:
            result.screenshot_paths.append(screenshot_path)

        # 結果判定
        if result.steps_failed > 0:
            result.status = "failed" if result.steps_passed == 0 else "success"
            # 半分以上失敗の場合は failed
            if result.steps_failed > result.steps_passed:
                result.status = "failed"
        result.retry_count = len(result.recovery_actions)
        result.duration_seconds = time.time() - start_time
        result.finished_at = datetime.now().isoformat()

        return result

    def _execute_step(
        self, step: OperationStep, runner: PlaywrightRunner
    ) -> bool:
        """
        1ステップを実行する。

        ステップのアクションテキストを解析して適切なブラウザ操作を行う。

        Args:
            step: 実行するステップ
            runner: Playwright ランナー

        Returns:
            bool: 成功かどうか
        """
        action_lower = step.action.lower()

        # ===== ナビゲーション =====
        if any(kw in action_lower for kw in ["ページを開く", "画面を開く", "遷移", "navigate"]):
            # URLパターンを抽出
            import re
            url_match = re.search(r"(/[\w/-]+)", step.action)
            if url_match:
                return runner.navigate(url_match.group(1), step.step_no)
            return True  # URLが分からない場合はスキップ

        # ===== クリック =====
        if any(kw in action_lower for kw in [
            "クリック", "押す", "タップ", "選択", "click", "tap", "select"
        ]):
            # UI要素名からセレクターを推定
            selector = self._infer_selector(step)
            return runner.click(selector, step.step_no)

        # ===== フォーム入力 =====
        if any(kw in action_lower for kw in [
            "入力", "記入", "fill", "type", "input"
        ]):
            selector, value = self._infer_input(step)
            if selector and value:
                return runner.fill_form(selector, value, step.step_no)
            return True

        # ===== 送信 =====
        if any(kw in action_lower for kw in ["送信", "保存", "submit", "save"]):
            return runner.click(
                'button[type="submit"], button:has-text("保存"), button:has-text("送信")',
                step.step_no
            )

        # ===== 確認・検証 =====
        if any(kw in action_lower for kw in [
            "確認", "表示", "verify", "check", "assert", "期待"
        ]):
            # エラー状態を確認
            error = runner.check_error_state()
            return error is None

        # ===== 待機 =====
        if any(kw in action_lower for kw in ["待機", "wait", "ローディング"]):
            time.sleep(1)
            return True

        # ===== 未知のアクション =====
        # スクリーンショットを撮ってスキップ
        runner.take_screenshot(
            f"unknown_step_{step.step_no}",
            step.step_no
        )
        return True  # 未知のアクションはスキップ扱い

    def _infer_selector(self, step: OperationStep) -> str:
        """
        ステップ情報からクリック対象のセレクターを推定する。

        UI要素名がある場合はそれを優先する。
        """
        if step.ui_element:
            # UI要素名から一般的なセレクターを推定
            element = step.ui_element
            return (
                f'button:has-text("{element}"), '
                f'a:has-text("{element}"), '
                f'[data-testid="{element}"], '
                f'[aria-label="{element}"]'
            )

        # アクションテキストから推定
        action = step.action
        if "新規作成" in action or "追加" in action:
            return 'button:has-text("新規作成"), button:has-text("追加"), a:has-text("新規")'
        if "削除" in action:
            return 'button:has-text("削除"), [data-testid="delete-btn"]'
        if "編集" in action:
            return 'button:has-text("編集"), a:has-text("編集")'
        if "検索" in action:
            return 'button:has-text("検索"), input[type="search"]'

        return 'button[type="button"]'

    def _infer_input(self, step: OperationStep) -> tuple[str, str]:
        """
        ステップ情報からフォーム入力のセレクターと値を推定する。
        """
        # アクションテキストからフィールド名を推定
        action = step.action
        if "名前" in action or "ホテル名" in action:
            return ('input[name="name"], input[placeholder*="名前"]', "テストホテル")
        if "メールアドレス" in action or "メール" in action:
            return ('input[type="email"]', self._config.e2e_test_email)
        if "パスワード" in action:
            return ('input[type="password"]', self._config.e2e_test_password)
        if "電話番号" in action:
            return ('input[name="phone"], input[type="tel"]', "03-0000-0000")
        if "住所" in action:
            return ('input[name="address"]', "東京都渋谷区テスト1-1-1")
        if "料金" in action or "価格" in action:
            return ('input[name="price"], input[type="number"]', "10000")

        # UI要素名があれば使用
        if step.ui_element:
            return (f'input[name="{step.ui_element}"], input[placeholder*="{step.ui_element}"]', "テスト入力値")

        return ("", "")

    def _save_results(self, output_dir: Path) -> None:
        """実行結果をJSONとMarkdownで保存する"""
        # JSON保存
        json_path = output_dir / "e2e_results.json"
        json_data = [
            {
                "scenario_id": r.scenario_id,
                "scenario_name": r.scenario_name,
                "usecase_id": r.usecase_id,
                "status": r.status,
                "steps_total": r.steps_total,
                "steps_passed": r.steps_passed,
                "steps_failed": r.steps_failed,
                "retry_count": r.retry_count,
                "duration_seconds": r.duration_seconds,
                "error_messages": r.error_messages,
                "recovery_actions": r.recovery_actions,
                "screenshot_paths": r.screenshot_paths,
                "started_at": r.started_at,
                "finished_at": r.finished_at,
            }
            for r in self._results
        ]
        json_path.write_text(
            json.dumps(json_data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        # Markdown保存
        md_path = output_dir / "e2e_results.md"
        self._save_markdown_report(md_path)

    def _save_markdown_report(self, output_path: Path) -> None:
        """Markdownレポートを生成して保存する"""
        total = len(self._results)
        success = sum(1 for r in self._results if r.status == "success")
        failed = sum(1 for r in self._results if r.status == "failed")
        skipped = sum(1 for r in self._results if r.status == "skipped")
        total_duration = sum(r.duration_seconds for r in self._results)

        content = f"""# E2Eテスト実行結果

**実行日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## サマリー

| 項目 | 値 |
|-----|---|
| 総シナリオ数 | {total} |
| 成功 | {success} ✅ |
| 失敗 | {failed} ❌ |
| スキップ | {skipped} ⏭️ |
| 成功率 | {success/total*100:.1f}% |
| 総実行時間 | {total_duration:.1f}秒 |

## シナリオ別結果

| シナリオID | シナリオ名 | ステータス | ステップ | リトライ | 時間 |
|-----------|----------|---------|---------|---------|-----|
"""
        for r in self._results:
            status_icon = {"success": "✅", "failed": "❌", "skipped": "⏭️"}.get(r.status, "?")
            content += (
                f"| {r.scenario_id} | {r.scenario_name} | {status_icon} {r.status} "
                f"| {r.steps_passed}/{r.steps_total} | {r.retry_count} "
                f"| {r.duration_seconds:.1f}s |\n"
            )

        # 失敗シナリオの詳細
        failed_results = [r for r in self._results if r.status == "failed"]
        if failed_results:
            content += "\n## 失敗シナリオの詳細\n\n"
            for r in failed_results:
                content += f"### ❌ {r.scenario_id}: {r.scenario_name}\n\n"
                for err in r.error_messages:
                    content += f"- {err}\n"
                if r.recovery_actions:
                    content += "\n**リカバリー試行**:\n"
                    for ra in r.recovery_actions:
                        content += f"- {ra}\n"
                content += "\n"

        output_path.write_text(content, encoding="utf-8")

    def _print_summary(self) -> None:
        """実行サマリーをコンソールに出力する"""
        total = len(self._results)
        success = sum(1 for r in self._results if r.status == "success")
        failed = sum(1 for r in self._results if r.status == "failed")

        table = Table(title="E2Eテスト結果サマリー", show_header=True)
        table.add_column("項目", style="bold")
        table.add_column("値")

        table.add_row("総シナリオ数", str(total))
        table.add_row("成功", f"[green]{success}[/green]")
        table.add_row("失敗", f"[red]{failed}[/red]")
        table.add_row(
            "成功率",
            f"[{'green' if success/total >= 0.8 else 'yellow'}]{success/total*100:.1f}%[/]"
        )

        self._console.print("\n")
        self._console.print(table)
