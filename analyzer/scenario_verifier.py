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
from .screen_analyzer import ScreenSpec, UIElement


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
    2. 対応する画面のScreenSpecと突き合わせ
    3. 不整合を検出してレポート
    4. LLMを使って修正版シナリオを生成
    """

    def __init__(self, llm_provider: LLMProvider = None, save_callback=None):
        self._llm = llm_provider
        self._save_callback = save_callback

    def verify_all(
        self,
        scenarios: list[OperationScenario],
        screen_specs: list[ScreenSpec],
        usecases: list[Usecase],
    ) -> list[VerificationResult]:
        """全シナリオを検証する"""
        # 画面仕様のインデックスを構築
        screen_by_route = {s.route_path: s for s in screen_specs}
        # APIから画面を逆引き
        api_to_screens = self._build_api_index(screen_specs)
        # UCからルートを取得
        uc_map = {uc.id: uc for uc in usecases}

        results = []
        for sc in scenarios:
            result = self._verify_scenario(sc, screen_by_route, api_to_screens, uc_map)
            results.append(result)

        return results

    def fix_scenarios(
        self,
        scenarios: list[OperationScenario],
        screen_specs: list[ScreenSpec],
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
        screen_by_route = {s.route_path: s for s in screen_specs}
        api_to_screens = self._build_api_index(screen_specs)
        uc_map = {uc.id: uc for uc in usecases}

        targets = [(sc, next((r for r in results if r.scenario_id == sc.scenario_id), None))
                   for sc in scenarios]
        to_fix = sum(1 for _, r in targets if r and r.issues and _.scenario_id not in already_fixed)

        import sys
        if already_fixed:
            print(f"  前回修正済み: {len(already_fixed)}件をスキップ", file=sys.stderr, flush=True)

        # 「対応画面なし」でもナビゲーション情報を使って修正するため、全画面のナビを集約
        all_nav_labels = set()
        for spec in screen_specs:
            for n in spec.shared_nav_items:
                all_nav_labels.add(n.label)

        fixed = []
        fix_count = 0
        for sc, result in targets:
            if result and result.issues and sc.scenario_id not in already_fixed:
                fix_count += 1
                print(f"  [{fix_count}/{to_fix}] {sc.scenario_id} ({len(result.issues)}件の問題)...", file=sys.stderr, flush=True)
                fixed_sc = self._fix_scenario_with_llm(sc, result, screen_by_route, api_to_screens, uc_map, all_nav_labels)
                fixed.append(fixed_sc)
            else:
                fixed.append(sc)

            # 10件ごとに中間保存（コールバックがあれば）
            if self._save_callback and fix_count > 0 and fix_count % 10 == 0:
                self._save_callback(fixed, scenarios[len(fixed):])

        return fixed

    def _build_api_index(self, screen_specs: list[ScreenSpec]) -> dict[str, list[ScreenSpec]]:
        """APIエンドポイント → 画面のインデックス（正規化パスで構築）"""
        index: dict[str, list[ScreenSpec]] = {}
        for spec in screen_specs:
            for api in spec.api_actions.values():
                if api:
                    path = self._normalize_api_path(api)
                    index.setdefault(path, []).append(spec)
            for btn in spec.action_buttons:
                if btn.api_call:
                    path = self._normalize_api_path(btn.api_call)
                    index.setdefault(path, []).append(spec)
        return index

    @staticmethod
    def _normalize_api_path(api_str: str) -> str:
        """APIパスを正規化: メソッド除去、パラメータ除去、末尾のリソース名を抽出"""
        path = api_str.split(" ", 1)[-1] if " " in api_str else api_str
        # /api/v1/owner/hotels/{id} → hotels
        # パラメータ部分を除去
        path = re.sub(r"/\{[^}]+\}", "", path)
        path = re.sub(r"/:[^/]+", "", path)
        return path

    @staticmethod
    def _extract_resource_name(path: str) -> str:
        """パスから末尾のリソース名を抽出"""
        normalized = re.sub(r"/\{[^}]+\}", "", path)
        normalized = re.sub(r"/:[^/]+", "", normalized)
        parts = [p for p in normalized.split("/") if p and p not in ("api", "v1", "v2")]
        return parts[-1] if parts else ""

    def _find_matching_screens(
        self,
        scenario: OperationScenario,
        screen_by_route: dict[str, ScreenSpec],
        api_to_screens: dict[str, list[ScreenSpec]],
        uc_map: dict[str, Usecase],
    ) -> list[ScreenSpec]:
        """シナリオに関連する画面を特定する（柔軟マッチング）"""
        matched = []
        all_screens = list(screen_by_route.values())

        # 1. frontend_url から直接マッチ
        if scenario.frontend_url:
            url = scenario.frontend_url
            if url in screen_by_route:
                matched.append(screen_by_route[url])
            else:
                # パラメータ部分を正規化して部分一致
                for route, spec in screen_by_route.items():
                    norm_url = re.sub(r"/\{[^}]+\}", "", url).rstrip("/")
                    norm_route = re.sub(r"/:[^/]+", "", route).rstrip("/")
                    if norm_url and norm_route and (norm_url in norm_route or norm_route in norm_url):
                        if spec not in matched:
                            matched.append(spec)

        # 2. ユースケースの related_routes からAPIリソース名で突き合わせ
        uc = uc_map.get(scenario.usecase_id)
        if uc:
            for route in uc.related_routes:
                norm_path = self._normalize_api_path(route)
                # 完全一致
                for screen in api_to_screens.get(norm_path, []):
                    if screen not in matched:
                        matched.append(screen)

                # リソース名ベースの部分一致
                resource = self._extract_resource_name(route)
                if resource:
                    for screen in all_screens:
                        screen_resources = set()
                        for api in list(screen.api_actions.values()) + [b.api_call for b in screen.action_buttons]:
                            if api:
                                sr = self._extract_resource_name(api)
                                if sr:
                                    screen_resources.add(sr)
                        # リソース名の部分一致（hotel/hotels, booking/bookings等）
                        for sr in screen_resources:
                            if resource.rstrip("s") == sr.rstrip("s") or resource in sr or sr in resource:
                                if screen not in matched:
                                    matched.append(screen)

        return matched

    def _verify_scenario(
        self,
        scenario: OperationScenario,
        screen_by_route: dict[str, ScreenSpec],
        api_to_screens: dict[str, list[ScreenSpec]],
        uc_map: dict[str, Usecase],
    ) -> VerificationResult:
        """単一シナリオを検証する"""
        matched_screens = self._find_matching_screens(scenario, screen_by_route, api_to_screens, uc_map)
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

        # 全画面のUI要素を集約
        all_buttons = []
        all_fields = []
        all_menus = []
        all_modals = []
        all_tabs = []
        for screen in matched_screens:
            all_buttons.extend(screen.action_buttons)
            all_fields.extend(screen.form_fields)
            all_menus.extend(screen.shared_nav_items)
            all_modals.extend(screen.modals)
            all_tabs.extend(screen.tabs)

        button_labels = {b.label for b in all_buttons}
        field_labels = {f.label for f in all_fields}
        menu_labels = {m.label for m in all_menus}
        modal_names = set(all_modals)
        tab_names = set(all_tabs)
        all_labels = button_labels | field_labels | menu_labels | modal_names | tab_names

        for step in scenario.steps:
            if step.actor == "システム":
                verified += 1
                continue

            step_issues = self._verify_step(
                step, scenario.scenario_id,
                all_labels, button_labels, field_labels, menu_labels,
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
        screens: list[ScreenSpec],
    ) -> list[VerificationIssue]:
        """ステップ内のUI要素参照を検証する"""
        issues = []
        action = step.action

        # 「」で囲まれた要素名を抽出
        quoted = re.findall(r"「(.+?)」", action)
        for element_name in quoted:
            if not self._find_element_match(element_name, all_labels):
                # 類似候補を探す
                suggestion = self._find_similar(element_name, all_labels)
                issues.append(VerificationIssue(
                    scenario_id=scenario_id,
                    step_no=step.step_no,
                    issue_type="missing_element",
                    description=f"UI要素「{element_name}」が画面仕様に見つかりません",
                    action_text=action,
                    suggestion=f"類似: {suggestion}" if suggestion else "",
                ))

        # クリック/タップ系アクションでボタン名を検証
        click_patterns = re.findall(r"(?:クリック|タップ|押す|選択)(?:する)?", action)
        if click_patterns and not quoted:
            # 具体的なUI要素名が引用なしで言及されているか
            for label in button_labels | menu_labels:
                if label in action:
                    break
            else:
                # ボタン名が見つからない場合は警告レベル
                pass

        return issues

    def _find_element_match(self, name: str, all_labels: set[str]) -> bool:
        """要素名が画面仕様に存在するか（部分一致含む）"""
        if name in all_labels:
            return True
        # 部分一致
        for label in all_labels:
            if name in label or label in name:
                return True
        return False

    def _find_similar(self, name: str, all_labels: set[str], threshold: int = 3) -> str:
        """類似する要素名を探す"""
        candidates = []
        for label in all_labels:
            # 共通文字数で類似度判定
            common = sum(1 for c in name if c in label)
            if common >= min(len(name), threshold):
                candidates.append(label)
        return ", ".join(candidates[:3])

    def _fix_scenario_with_llm(
        self,
        scenario: OperationScenario,
        result: VerificationResult,
        screen_by_route: dict[str, ScreenSpec],
        api_to_screens: dict[str, list[ScreenSpec]],
        uc_map: dict[str, Usecase],
        all_nav_labels: set[str] = None,
    ) -> OperationScenario:
        """LLMでシナリオを修正する"""
        matched_screens = self._find_matching_screens(scenario, screen_by_route, api_to_screens, uc_map)

        # 画面のUI要素をテキスト化
        screen_context = ""
        if not matched_screens and all_nav_labels:
            screen_context += f"\n（対応する画面仕様なし。共有ナビゲーション項目: {', '.join(sorted(all_nav_labels)[:20])}）\n"
            screen_context += "注意: 対応する画面が見つからないため、存在しないメニューやボタンを推測で使わないでください。\n"
            screen_context += "APIエンドポイントへの直接アクセスとして記述してください。\n"
        for screen in matched_screens:
            screen_context += f"\n画面: {screen.route_path} ({screen.page_title})\n"
            if screen.action_buttons:
                screen_context += f"  ボタン: {', '.join(b.label for b in screen.action_buttons)}\n"
            if screen.form_fields:
                screen_context += f"  フォーム: {', '.join(f.label for f in screen.form_fields)}\n"
            if screen.tabs:
                screen_context += f"  タブ: {', '.join(screen.tabs)}\n"
            if screen.modals:
                screen_context += f"  モーダル: {', '.join(screen.modals)}\n"
            if screen.shared_nav_items:
                screen_context += f"  ナビ: {', '.join(n.label for n in screen.shared_nav_items)}\n"

        # 問題点をテキスト化
        issues_text = "\n".join([
            f"  Step {i.step_no}: {i.description} (アクション: {i.action_text}){' → ' + i.suggestion if i.suggestion else ''}"
            for i in result.issues
        ])

        # 現在のステップ
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
        # JSON
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

        # Markdown
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
