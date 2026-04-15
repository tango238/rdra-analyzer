"""
操作シナリオ（アクティビティ）構造化モジュール

各ユースケースに対して操作シナリオ（アクティビティ）を抽出し、
JSONとしてシリアライズする。
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from llm.provider import LLMProvider
from .usecase_extractor import Usecase


@dataclass
class OperationStep:
    """操作シナリオの1ステップ"""
    step_no: int            # ステップ番号
    actor: str              # このステップのアクター（「ユーザー」「システム」）
    action: str             # アクション（「ホテル一覧を開く」など）
    expected_result: str    # 期待結果
    ui_element: str = ""    # 操作するUI要素（任意）


@dataclass
class OperationScenario:
    """ユースケースの操作シナリオ（アクティビティ）"""
    usecase_id: str                 # 対応するユースケースID
    usecase_name: str               # ユースケース名
    scenario_id: str                # SC-001-01 形式
    scenario_name: str              # シナリオ名（正常系・エラー系・境界値など）
    scenario_type: str              # "normal" | "error" | "boundary"
    steps: list[OperationStep]      # 操作ステップ一覧
    variations: list[str]           # バリエーション（入力値のパターンなど）
    frontend_url: str = ""          # 対応するフロントエンドURL
    api_endpoint: str = ""          # 主に使用するAPIエンドポイント


class ScenarioBuilder:
    """
    ユースケースから操作シナリオを構築するクラス。

    各ユースケースに対して:
    1. 正常系シナリオ
    2. エラー系シナリオ（バリデーション・権限エラーなど）
    を生成する。

    screen_specs が提供されている場合、実際の画面UI要素に基づいて
    シナリオのステップを生成する。
    """

    def __init__(self, llm_provider: LLMProvider, screen_specs: list = None):
        self._llm = llm_provider
        self._screen_specs = screen_specs or []
        self._screen_model_index = self._build_screen_model_index()

    def build(self, usecases: list[Usecase]) -> list[OperationScenario]:
        """
        ユースケースリストから操作シナリオを構築する。

        Args:
            usecases: 抽出済みユースケース一覧

        Returns:
            list[OperationScenario]: 操作シナリオ一覧
        """
        all_scenarios: list[OperationScenario] = []

        for usecase in usecases:
            scenarios = self._build_for_usecase(usecase)
            all_scenarios.extend(scenarios)

        return all_scenarios

    def build_and_validate_for_usecase(self, usecase: Usecase, max_retries: int = 1) -> list[OperationScenario]:
        """
        1つのユースケースに対してシナリオを生成し、画面仕様と突き合わせ検証する。
        問題があれば問題点を明示してLLMに再生成させる。

        Args:
            usecase: 対象ユースケース
            max_retries: 検証失敗時の再生成回数（デフォルト1回）

        Returns:
            list[OperationScenario]: 検証済みシナリオ
        """
        if not self._screen_specs:
            return self._build_for_usecase(usecase)

        from .scenario_verifier import ScenarioVerifier
        verifier = ScenarioVerifier()

        matched_screens = self._find_screens_for_usecase(usecase)
        if not matched_screens:
            # 対応画面なしの場合は検証スキップ
            return self._build_for_usecase(usecase)

        # 画面のUI要素を集約
        all_labels = set()
        button_labels = set()
        field_labels = set()
        for screen in matched_screens:
            for a in screen.actions:
                button_labels.add(a.label)
                all_labels.add(a.label)
            for section in screen.sections:
                for f in section.input_fields:
                    field_labels.add(f.label)
                    all_labels.add(f.label)

        scenarios = self._build_for_usecase(usecase)

        for attempt in range(max_retries + 1):
            # 各シナリオを検証
            issues_by_scenario = {}
            for sc in scenarios:
                issues = []
                for step in sc.steps:
                    if step.actor == "システム":
                        continue
                    step_issues = verifier._verify_step(
                        step, sc.scenario_id,
                        all_labels, button_labels, field_labels,
                        matched_screens,
                    )
                    issues.extend(step_issues)
                if issues:
                    issues_by_scenario[sc.scenario_id] = issues

            if not issues_by_scenario:
                break  # 全シナリオ検証OK

            if attempt >= max_retries:
                break  # リトライ上限

            # 問題のあるシナリオを再生成
            screen_context = self._build_screen_context(matched_screens)
            issues_text = ""
            for sc_id, sc_issues in issues_by_scenario.items():
                issues_text += f"\n{sc_id}:\n"
                for issue in sc_issues:
                    issues_text += f"  - Step {issue.step_no}: {issue.description}\n"
                    if issue.suggestion:
                        issues_text += f"    候補: {issue.suggestion}\n"

            scenarios = self._rebuild_with_issues(usecase, screen_context, issues_text)

        return scenarios

    def _rebuild_with_issues(
        self, usecase: Usecase, screen_context: str, issues_text: str
    ) -> list[OperationScenario]:
        """検証で見つかった問題を含めてシナリオを再生成する"""
        system_prompt = """あなたはRDRA専門家です。操作シナリオを生成してください。

前回の生成で画面仕様との不整合が見つかりました。
画面仕様に記載されたUI要素のみを使用して、修正版を生成してください。

以下のJSON形式で回答してください:
{
  "scenarios": [
    {
      "scenario_name": "シナリオ名",
      "scenario_type": "normal|error|boundary",
      "frontend_url": "/hotels",
      "api_endpoint": "GET /api/v2/hotels",
      "steps": [
        {
          "step_no": 1,
          "actor": "ユーザー|システム",
          "action": "アクション説明",
          "expected_result": "期待結果",
          "ui_element": "UI要素名（任意）"
        }
      ],
      "variations": ["バリエーション1"]
    }
  ]
}

重要ルール:
- 「実際の画面仕様」に記載されたUI要素（ボタン名、フォーム項目名、タブ名、メニュー名）のみを使用
- 画面仕様に存在しないボタンやメニューを捏造しない
- 「」で囲むUI要素名は画面仕様のラベルと完全に一致させる
- 日本語で出力"""

        user_message = f"""
## ユースケース
- ID: {usecase.id}
- 名前: {usecase.name}
- アクター: {usecase.actor}
- 説明: {usecase.description}
- 事前条件: {', '.join(usecase.preconditions)}
- 関連ルート: {', '.join(usecase.related_routes[:5])}
- 関連エンティティ: {', '.join(usecase.related_entities)}
{screen_context}

## 前回の検証で見つかった問題
{issues_text}

上記の問題を修正し、画面仕様に忠実なシナリオを生成してください。
"""

        response = self._llm.complete_simple(
            user_message=user_message,
            system_prompt=system_prompt,
        )

        return self._parse_scenarios(response, usecase)

    def _build_screen_model_index(self) -> dict:
        """画面仕様のモデル名インデックスを構築"""
        index = {}
        for spec in self._screen_specs:
            for model in getattr(spec, "related_models", []):
                index.setdefault(model, []).append(spec)
        return index

    def _find_screens_for_usecase(self, usecase: Usecase) -> list:
        """ユースケースに関連する画面仕様を特定する"""
        matched = []
        # related_entities でマッチ
        for entity in usecase.related_entities:
            for spec in self._screen_model_index.get(entity, []):
                if spec not in matched:
                    matched.append(spec)
        # related_usecases でマッチ
        if not matched:
            for spec in self._screen_specs:
                for uc_name in getattr(spec, "related_usecases", []):
                    if usecase.name in uc_name or uc_name in usecase.name:
                        if spec not in matched:
                            matched.append(spec)
        return matched

    def _build_screen_context(self, screens: list) -> str:
        """画面仕様をLLMプロンプト用テキストに変換する"""
        if not screens:
            return ""

        lines = ["\n## 実際の画面仕様（この情報に基づいてステップを生成してください）"]
        for screen in screens[:5]:  # 最大5画面
            lines.append(f"\n### 画面: {screen.screen_id} ({screen.title})")
            for section in screen.sections:
                lines.append(f"  セクション: {section.section_name}")
                for f in section.input_fields:
                    label = f.label
                    if f.type == "data_table":
                        col_labels = [c.get("label", "") for c in f.columns[:5]]
                        label += f" [列: {', '.join(col_labels)}]"
                    lines.append(f"    - {label} ({f.type})")
            if screen.actions:
                lines.append(f"  アクション: {', '.join(a.label for a in screen.actions)}")

        return "\n".join(lines)

    def _build_for_usecase(self, usecase: Usecase) -> list[OperationScenario]:
        """
        1つのユースケースに対して操作シナリオを生成する。

        LLMを使って正常系・エラー系のシナリオを生成する。
        """
        # 関連画面を検索
        matched_screens = self._find_screens_for_usecase(usecase)
        screen_context = self._build_screen_context(matched_screens)
        has_screens = bool(screen_context)
        api_only = not has_screens and self._screen_specs  # 画面仕様はあるが該当画面なし → API操作のみ

        screen_rule = ""
        if api_only:
            screen_rule = """
重要ルール（必ず守ること）:
- このユースケースには対応するフロントエンド画面が存在しません
- UIのボタン、メニュー、フォームなどの画面要素を使ったステップは書かないでください
- 全てのステップをAPIリクエスト/レスポンスベースで記述してください
- ステップのアクターは「クライアント」と「システム」を使ってください
- アクション例: 「POST /api/v2/xxx にリクエストを送信する」「レスポンス200を返す」"""
        elif has_screens:
            screen_rule = """
重要ルール（必ず守ること）:
- 「実際の画面仕様」に記載されたUI要素（ボタン名、フォーム項目名、タブ名、メニュー名）のみを使用すること
- 画面仕様に存在しないボタンやメニューを捏造しないこと
- ナビゲーションは画面仕様のナビゲーション項目に基づくこと
- フォーム入力ステップは画面仕様のフォーム項目に基づくこと"""

        system_prompt = f"""あなたはRDRA専門家です。ユースケースに対する操作シナリオ（アクティビティ）を生成してください。

以下のJSON形式で回答してください:
{{
  "scenarios": [
    {{
      "scenario_name": "シナリオ名",
      "scenario_type": "normal|error|boundary",
      "frontend_url": "/hotels",
      "api_endpoint": "GET /api/v2/hotels",
      "steps": [
        {{
          "step_no": 1,
          "actor": "ユーザー|システム",
          "action": "アクション説明",
          "expected_result": "期待結果",
          "ui_element": "UI要素名（任意）"
        }}
      ],
      "variations": ["バリエーション1", "バリエーション2"]
    }}
  ]
}}

ルール:
- 正常系（normal）は必ず含める
- エラー系（error）はバリデーション・権限エラーなど
- UI要素名はボタン・フォーム・テーブルなど具体的に
- ステップは5〜10個程度
- 日本語で出力
{screen_rule}"""

        user_message = f"""
## ユースケース
- ID: {usecase.id}
- 名前: {usecase.name}
- アクター: {usecase.actor}
- 説明: {usecase.description}
- 事前条件: {', '.join(usecase.preconditions)}
- 関連ルート: {', '.join(usecase.related_routes[:5])}
- 関連エンティティ: {', '.join(usecase.related_entities)}
- カテゴリ: {usecase.category}
{screen_context}

このユースケースの操作シナリオを生成してください。
正常系と主要なエラー系を含めてください。
{"画面仕様に記載されたUI要素のみを使用してください。" if has_screens else ""}
"""

        response = self._llm.complete_simple(
            user_message=user_message,
            system_prompt=system_prompt,
        )

        return self._parse_scenarios(response, usecase)

    def _parse_scenarios(
        self, response: str, usecase: Usecase
    ) -> list[OperationScenario]:
        """LLMレスポンスをOperationScenarioオブジェクトに変換する"""
        scenarios: list[OperationScenario] = []

        # コードブロックを除去
        cleaned = re.sub(r"```(?:json)?\s*", "", response).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        try:
            data = json.loads(cleaned)
            for idx, item in enumerate(data.get("scenarios", []), start=1):
                steps = [
                    OperationStep(
                        step_no=s.get("step_no", i + 1),
                        actor=s.get("actor", "ユーザー"),
                        action=s.get("action", ""),
                        expected_result=s.get("expected_result", ""),
                        ui_element=s.get("ui_element", ""),
                    )
                    for i, s in enumerate(item.get("steps", []))
                ]
                scenario = OperationScenario(
                    usecase_id=usecase.id,
                    usecase_name=usecase.name,
                    scenario_id=f"{usecase.id}-SC{idx:02d}",
                    scenario_name=item.get("scenario_name", f"シナリオ{idx}"),
                    scenario_type=item.get("scenario_type", "normal"),
                    steps=steps,
                    variations=item.get("variations", []),
                    frontend_url=item.get("frontend_url", ""),
                    api_endpoint=item.get("api_endpoint", ""),
                )
                scenarios.append(scenario)
        except (json.JSONDecodeError, KeyError):
            # フォールバック: シンプルな正常系シナリオを生成
            scenarios = [self._create_fallback_scenario(usecase)]

        return scenarios

    def _create_fallback_scenario(self, usecase: Usecase) -> OperationScenario:
        """LLMパース失敗時のフォールバックシナリオ"""
        steps = [
            OperationStep(
                step_no=1,
                actor="ユーザー",
                action=f"{usecase.name}ページを開く",
                expected_result="ページが表示される",
            ),
            OperationStep(
                step_no=2,
                actor="ユーザー",
                action="必要な情報を入力する",
                expected_result="入力フォームが表示される",
            ),
            OperationStep(
                step_no=3,
                actor="システム",
                action="APIリクエストを送信する",
                expected_result=f"{usecase.name}が完了する",
            ),
        ]

        return OperationScenario(
            usecase_id=usecase.id,
            usecase_name=usecase.name,
            scenario_id=f"{usecase.id}-SC01",
            scenario_name="正常系",
            scenario_type="normal",
            steps=steps,
            variations=[],
            frontend_url="",
            api_endpoint=usecase.related_routes[0] if usecase.related_routes else "",
        )

    def save_to_json(
        self,
        usecases: list[Usecase],
        scenarios: list[OperationScenario],
        output_path: Path,
    ) -> None:
        """
        ユースケースと操作シナリオをJSON形式で保存する。

        Args:
            usecases: ユースケース一覧
            scenarios: 操作シナリオ一覧
            output_path: 出力ファイルパス
        """
        # ユースケースをシリアライズ
        usecase_data = [
            {
                "id": uc.id,
                "name": uc.name,
                "actor": uc.actor,
                "description": uc.description,
                "preconditions": uc.preconditions,
                "postconditions": uc.postconditions,
                "related_routes": uc.related_routes,
                "related_pages": uc.related_pages,
                "related_entities": uc.related_entities,
                "related_controllers": getattr(uc, "related_controllers", []),
                "related_views": getattr(uc, "related_views", []),
                "category": uc.category,
                "priority": uc.priority,
            }
            for uc in usecases
        ]

        # シナリオをシリアライズ
        scenario_data = [
            {
                "scenario_id": sc.scenario_id,
                "usecase_id": sc.usecase_id,
                "usecase_name": sc.usecase_name,
                "scenario_name": sc.scenario_name,
                "scenario_type": sc.scenario_type,
                "frontend_url": sc.frontend_url,
                "api_endpoint": sc.api_endpoint,
                "steps": [
                    {
                        "step_no": s.step_no,
                        "actor": s.actor,
                        "action": s.action,
                        "expected_result": s.expected_result,
                        "ui_element": s.ui_element,
                    }
                    for s in sc.steps
                ],
                "variations": sc.variations,
            }
            for sc in scenarios
        ]

        output = {
            "metadata": {
                "total_usecases": len(usecases),
                "total_scenarios": len(scenarios),
            },
            "usecases": usecase_data,
            "scenarios": scenario_data,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
