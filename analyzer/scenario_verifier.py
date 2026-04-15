"""
操作シナリオ × 画面仕様 突き合わせ検証モジュール

操作シナリオの各ステップが実際の画面UI要素と整合しているか検証し、
不整合があればLLMを使って修正する。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from llm.provider import LLMProvider
from .usecase_extractor import Usecase
from .scenario_builder import OperationScenario, OperationStep
from .view_model import ViewScreen


@dataclass
class VerificationIssue:
    """検証で見つかった問題"""
    scenario_id: str
    step_no: int
    issue_type: str         # missing_element, wrong_label, no_matching_screen, missing_api
    description: str
    action_text: str        # 問題のあるステップのアクション
    suggestion: str = ""    # 修正提案


@dataclass
class VerificationResult:
    """シナリオ検証結果"""
    scenario_id: str
    usecase_id: str
    total_steps: int
    verified_steps: int     # UIと整合したステップ数
    issues: list[VerificationIssue] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return self.verified_steps / self.total_steps


class ScenarioVerifier:
    """
    操作シナリオを画面仕様と突き合わせて検証するクラス。

    1. シナリオの各ステップに言及されるUI要素を抽出
    2. 対応する画面の ViewScreen と突き合わせ
    3. 不整合を検出してレポート
    4. LLMを使って修正版シナリオを生成
    """

    def __init__(self, llm_provider: LLMProvider = None, save_callback=None):
        self._llm = llm_provider
        self._save_callback = save_callback

    def verify_all(
        self,
        scenarios: list[OperationScenario],
        screen_specs: list[ViewScreen],
        usecases: list[Usecase],
    ) -> list[VerificationResult]:
        """全シナリオを検証する"""
        screen_by_id = {s.screen_id: s for s in screen_specs}
        uc_map = {uc.id: uc for uc in usecases}

        results = []
        for sc in scenarios:
            result = self._verify_scenario(sc, screen_by_id, uc_map)
            results.append(result)

        return results

    def fix_scenarios(
        self,
        scenarios: list[OperationScenario],
        screen_specs: list[ViewScreen],
        usecases: list[Usecase],
        results: list[VerificationResult],
        already_fixed: set[str] = None,
    ) -> list[OperationScenario]:
        """検証結果をもとにLLMでシナリオを修正する。

        already_fixed: 前回修正済みのシナリオIDセット（再開時に使用）
        """
        if not self._llm:
            return scenarios

        already_fixed = already_fixed or set()
        screen_by_id = {s.screen_id: s for s in screen_specs}
        uc_map = {uc.id: uc for uc in usecases}

        targets = [(sc, next((r for r in results if r.scenario_id == sc.scenario_id), None))
                   for sc in scenarios]
        to_fix = sum(1 for _, r in targets if r and r.issues and _.scenario_id not in already_fixed)

        import sys
        if already_fixed:
            print(f"  前回修正済み: {len(already_fixed)}件をスキップ", file=sys.stderr, flush=True)

        fixed = []
        fix_count = 0
        for sc, result in targets:
            if result and result.issues and sc.scenario_id not in already_fixed:
                fix_count += 1
                print(f"  [{fix_count}/{to_fix}] {sc.scenario_id} ({len(result.issues)}件の問題)...", file=sys.stderr, flush=True)
                fixed_sc = self._fix_scenario_with_llm(sc, result, screen_by_id, uc_map)
                fixed.append(fixed_sc)
            else:
                fixed.append(sc)

            if self._save_callback and fix_count > 0 and fix_count % 10 == 0:
                self._save_callback(fixed, scenarios[len(fixed):])

        return fixed

    def _find_matching_screens(
        self,
        scenario: OperationScenario,
        screen_by_id: dict[str, ViewScreen],
        uc_map: dict[str, Usecase],
    ) -> list[ViewScreen]:
        """シナリオに関連する画面を特定する"""
        matched = []
        all_screens = list(screen_by_id.values())

        uc = uc_map.get(scenario.usecase_id)
        if not uc:
            return matched

        # ユースケース名で直接マッチ
        for screen in all_screens:
            for uc_name in screen.related_usecases:
                if uc.name in uc_name or uc_name in uc.name:
                    if screen not in matched:
                        matched.append(screen)

        # related_entities でマッチ
        if not matched:
            for screen in all_screens:
                for model in screen.related_models:
                    for entity in uc.related_entities:
                        if model == entity or model in entity or entity in model:
                            if screen not in matched:
                                matched.append(screen)

        return matched

    def _verify_scenario(
        self,
        scenario: OperationScenario,
        screen_by_id: dict[str, ViewScreen],
        uc_map: dict[str, Usecase],
    ) -> VerificationResult:
        """単一シナリオを検証する"""
        matched_screens = self._find_matching_screens(scenario, screen_by_id, uc_map)
        issues = []
        verified = 0

        if not matched_screens:
            issues.append(VerificationIssue(
                scenario_id=scenario.scenario_id,
                step_no=0,
                issue_type="no_matching_screen",
                description="対応する画面仕様が見つかりません",
                action_text="",
            ))
            return VerificationResult(
                scenario_id=scenario.scenario_id,
                usecase_id=scenario.usecase_id,
                total_steps=len(scenario.steps),
                verified_steps=0,
                issues=issues,
            )

        # 全画面の UI ラベルを集約
        all_labels = set()
        button_labels = set()
        field_labels = set()
        for screen in matched_screens:
            for action in screen.actions:
                button_labels.add(action.label)
                all_labels.add(action.label)
            for section in screen.sections:
                for f in section.input_fields:
                    field_labels.add(f.label)
                    all_labels.add(f.label)

        for step in scenario.steps:
            if step.actor == "システム":
                verified += 1
                continue
            step_issues = self._verify_step(
                step, scenario.scenario_id,
                all_labels, button_labels, field_labels, set(),
                matched_screens,
            )
            if step_issues:
                issues.extend(step_issues)
            else:
                verified += 1

        return VerificationResult(
            scenario_id=scenario.scenario_id,
            usecase_id=scenario.usecase_id,
            total_steps=len(scenario.steps),
            verified_steps=verified,
            issues=issues,
        )

    def _verify_step(
        self,
        step: OperationStep,
        scenario_id: str,
        all_labels: set[str],
        button_labels: set[str],
        field_labels: set[str],
        menu_labels: set[str],
        screens: list[ViewScreen],
    ) -> list[VerificationIssue]:
        """ステップ内のUI要素参照を検証する"""
        issues = []
        action = step.action

        # 「」で囲まれた要素名を抽出
        quoted = re.findall(r"「(.+?)」", action)
        for element_name in quoted:
            if not self._find_element_match(element_name, all_labels):
                suggestion = self._find_similar(element_name, all_labels)
                issues.append(VerificationIssue(
                    scenario_id=scenario_id,
                    step_no=step.step_no,
                    issue_type="missing_element",
                    description=f"UI要素「{element_name}」が画面仕様に見つかりません",
                    action_text=action,
                    suggestion=f"類似: {suggestion}" if suggestion else "",
                ))

        return issues

    def _find_element_match(self, name: str, all_labels: set[str]) -> bool:
        """要素名が画面仕様に存在するか（部分一致含む）"""
        if name in all_labels:
            return True
        for label in all_labels:
            if name in label or label in name:
                return True
        return False

    def _find_similar(self, name: str, all_labels: set[str], threshold: int = 3) -> str:
        """類似する要素名を探す"""
        candidates = []
        for label in all_labels:
            common = sum(1 for c in name if c in label)
            if common >= min(len(name), threshold):
                candidates.append(label)
        return ", ".join(candidates[:3])

    def _fix_scenario_with_llm(
        self,
        scenario: OperationScenario,
        result: VerificationResult,
        screen_by_id: dict[str, ViewScreen],
        uc_map: dict[str, Usecase],
    ) -> OperationScenario:
        """LLMでシナリオを修正する"""
        matched_screens = self._find_matching_screens(scenario, screen_by_id, uc_map)

        screen_context = ""
        for screen in matched_screens:
            screen_context += f"\n画面: {screen.screen_id} ({screen.title})\n"
            for section in screen.sections:
                screen_context += f"  セクション: {section.section_name}\n"
                for f in section.input_fields:
                    screen_context += f"    - {f.label} ({f.type})\n"
            if screen.actions:
                screen_context += f"  アクション: {', '.join(a.label for a in screen.actions)}\n"

        issues_text = "\n".join([
            f"  Step {i.step_no}: {i.description} (アクション: {i.action_text}){' → ' + i.suggestion if i.suggestion else ''}"
            for i in result.issues
        ])

        steps_text = "\n".join([
            f"  Step {s.step_no}: [{s.actor}] {s.action} → {s.expected_result}"
            for s in scenario.steps
        ])

        system_prompt = """あなたはRDRA専門家です。操作シナリオを実際の画面仕様に基づいて修正してください。

重要: 画面仕様に存在しないUI要素（ボタン、メニュー、フォーム項目）は使用しないでください。
実際に存在するUI要素のみを使ってステップを書き直してください。

以下のJSON形式で回答してください:
{
  "steps": [
    {
      "step_no": 1,
      "actor": "ユーザー|システム",
      "action": "修正後のアクション",
      "expected_result": "期待結果",
      "ui_element": "UI要素名"
    }
  ]
}"""

        user_message = f"""
## シナリオ
- ID: {scenario.scenario_id}
- ユースケース: {scenario.usecase_id} {scenario.usecase_name}
- 種別: {scenario.scenario_type}

## 現在のステップ
{steps_text}

## 検証で見つかった問題
{issues_text}

## 実際の画面仕様
{screen_context}

上記の画面仕様に基づいて、問題のあるステップを修正してください。
画面に存在するUI要素のみを使用してください。
"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=system_prompt,
            )
            return self._parse_fixed_scenario(response, scenario)
        except Exception:
            return scenario

    def _parse_fixed_scenario(
        self, response: str, original: OperationScenario
    ) -> OperationScenario:
        """LLMの修正レスポンスをパースする"""
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if not json_match:
            return original

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return original

        steps = []
        for st in data.get("steps", []):
            steps.append(OperationStep(
                step_no=st.get("step_no", 0),
                actor=st.get("actor", "ユーザー"),
                action=st.get("action", ""),
                expected_result=st.get("expected_result", ""),
                ui_element=st.get("ui_element", ""),
            ))

        if not steps:
            return original

        return OperationScenario(
            usecase_id=original.usecase_id,
            usecase_name=original.usecase_name,
            scenario_id=original.scenario_id,
            scenario_name=original.scenario_name,
            scenario_type=original.scenario_type,
            steps=steps,
            variations=original.variations,
            frontend_url=original.frontend_url,
            api_endpoint=original.api_endpoint,
        )

    @staticmethod
    def save_report(results: list[VerificationResult], output_path: Path) -> None:
        """検証レポートをJSON + Markdownで保存する"""
        json_data = {
            "metadata": {
                "total_scenarios": len(results),
                "scenarios_with_issues": sum(1 for r in results if r.issues),
                "total_issues": sum(len(r.issues) for r in results),
                "average_pass_rate": sum(r.pass_rate for r in results) / len(results) if results else 0,
            },
            "results": [
                {
                    "scenario_id": r.scenario_id,
                    "usecase_id": r.usecase_id,
                    "total_steps": r.total_steps,
                    "verified_steps": r.verified_steps,
                    "pass_rate": round(r.pass_rate, 2),
                    "issues": [
                        {
                            "step_no": i.step_no,
                            "issue_type": i.issue_type,
                            "description": i.description,
                            "action_text": i.action_text,
                            "suggestion": i.suggestion,
                        }
                        for i in r.issues
                    ],
                }
                for r in results
            ],
        }
        json_path = output_path.with_suffix(".json")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")

        md_lines = ["# シナリオ検証レポート\n"]
        meta = json_data["metadata"]
        md_lines.append(f"- シナリオ数: {meta['total_scenarios']}")
        md_lines.append(f"- 問題ありシナリオ: {meta['scenarios_with_issues']}")
        md_lines.append(f"- 総問題数: {meta['total_issues']}")
        md_lines.append(f"- 平均適合率: {meta['average_pass_rate']:.0%}\n")

        for r in results:
            if not r.issues:
                continue
            md_lines.append(f"## {r.scenario_id} ({r.usecase_id})")
            md_lines.append(f"適合率: {r.pass_rate:.0%} ({r.verified_steps}/{r.total_steps})\n")
            for i in r.issues:
                md_lines.append(f"- **Step {i.step_no}** [{i.issue_type}]: {i.description}")
                if i.suggestion:
                    md_lines.append(f"  - 提案: {i.suggestion}")
                md_lines.append(f"  - アクション: `{i.action_text}`")
            md_lines.append("")

        md_path = output_path.with_suffix(".md")
        md_path.write_text("\n".join(md_lines), encoding="utf-8")
