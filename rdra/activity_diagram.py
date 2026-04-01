"""
アクティビティ図（操作シナリオ）生成モジュール

操作シナリオの各ステップを Mermaid のsequenceDiagram または flowchart で表現する。
"""

from analyzer.scenario_builder import OperationScenario, OperationStep


class ActivityDiagramGenerator:
    """
    操作シナリオから Mermaid アクティビティ図を生成するクラス。

    シナリオの各ステップをシーケンス図として表現し、
    ユーザーとシステムの相互作用を可視化する。
    """

    def generate_sequence_diagram(self, scenario: OperationScenario, actor_name: str = "") -> str:
        """
        操作シナリオを Mermaid シーケンス図に変換する。

        Args:
            scenario: 操作シナリオ
            actor_name: ユースケースのアクター名（省略時はステップから推定）

        Returns:
            str: Mermaid sequenceDiagram 記法の文字列
        """
        # ユースケースのアクター名を使用（なければステップから推定）
        if not actor_name:
            for step in scenario.steps:
                if step.actor and step.actor != "システム":
                    actor_name = step.actor
                    break
        primary_actor = actor_name or "ユーザー"

        # 参加者定義を動的に構築
        lines = [
            "---",
            f"title: {scenario.scenario_id} - {scenario.scenario_name}",
            "---",
            "sequenceDiagram",
            "    autonumber",
            "",
            "    %% 参加者定義",
            f"    actor User as {self._safe_mermaid_text(primary_actor)}",
            "    participant UI as フロントエンド",
            "    participant API as バックエンドAPI",
            "    participant DB as データベース",
            "",
        ]

        for step in scenario.steps:
            step_comment = f"%% ステップ{step.step_no}: {step.action}"
            lines.append(f"    {step_comment}")

            if step.actor == "システム":
                # UI → API → DB のフロー
                safe_action = self._safe_mermaid_text(step.action)
                lines.append(f"    UI->>+API: {safe_action}")
                lines.append(f"    API->>+DB: クエリ実行")
                lines.append(f"    DB-->>-API: 結果返却")

                safe_result = self._safe_mermaid_text(step.expected_result)
                lines.append(f"    API-->>-UI: {safe_result}")
                lines.append(f"    UI-->>User: 画面更新")

            else:
                # システム以外は全てプライマリアクターとして扱う
                safe_action = self._safe_mermaid_text(step.action)
                lines.append(f"    User->>UI: {safe_action}")

                safe_result = self._safe_mermaid_text(step.expected_result)
                lines.append(f"    UI-->>User: {safe_result}")

            lines.append("")

        return "\n".join(lines)

    def generate_all_scenarios_flowchart(
        self, scenarios: list[OperationScenario]
    ) -> str:
        """
        全シナリオの概要を Mermaid flowchart で表現する。

        ユースケースIDごとにグループ化して表示する。

        Args:
            scenarios: 操作シナリオ一覧

        Returns:
            str: Mermaid flowchart の文字列
        """
        lines = [
            "---",
            "title: 操作シナリオ一覧",
            "---",
            "flowchart TD",
            "",
        ]

        # ユースケースIDでグループ化
        uc_groups: dict[str, list[OperationScenario]] = {}
        for sc in scenarios:
            uc_groups.setdefault(sc.usecase_id, []).append(sc)

        for uc_id, uc_scenarios in uc_groups.items():
            safe_uc_id = uc_id.replace("-", "_")
            uc_name = uc_scenarios[0].usecase_name if uc_scenarios else uc_id

            lines.append(f'    subgraph SG_{safe_uc_id}["{uc_id}: {uc_name}"]')

            for sc in uc_scenarios:
                safe_sc_id = sc.scenario_id.replace("-", "_")
                type_icon = {
                    "normal": "✅",
                    "error": "❌",
                    "boundary": "⚠️",
                }.get(sc.scenario_type, "📋")

                step_count = len(sc.steps)
                lines.append(
                    f'        {safe_sc_id}["{type_icon} {sc.scenario_name}\\n'
                    f'ステップ数: {step_count}"]'
                )

                # URL情報
                if sc.frontend_url:
                    url_id = f"{safe_sc_id}_url"
                    lines.append(
                        f'        {url_id}(["{sc.frontend_url}"])'
                    )
                    lines.append(f"        {safe_sc_id} -.-> {url_id}")

            lines.append("    end")
            lines.append("")

        # スタイル
        lines.append("    classDef normal fill:#e8f5e9,stroke:#4CAF50")
        lines.append("    classDef error fill:#ffebee,stroke:#F44336")
        lines.append("    classDef boundary fill:#fff3e0,stroke:#FF9800")

        for sc in scenarios:
            safe_sc_id = sc.scenario_id.replace("-", "_")
            lines.append(f"    class {safe_sc_id} {sc.scenario_type}")

        return "\n".join(lines)

    def _safe_mermaid_text(self, text: str) -> str:
        """
        Mermaid記法で安全に使用できるテキストに変換する。

        Mermaid では特定の文字が記法として解釈されるため、
        これらをエスケープまたは置換する。
        """
        if not text:
            return ""
        # 40文字以上は切り捨て（図が見やすくなるように）
        if len(text) > 40:
            text = text[:37] + "..."
        # Mermaid の特殊文字を置換
        text = text.replace('"', "'")
        text = text.replace("<", "＜")
        text = text.replace(">", "＞")
        text = text.replace("{", "｛")
        text = text.replace("}", "｝")
        return text

    def save_all(
        self,
        scenarios: list[OperationScenario],
        output_dir,
        uc_actor_map: dict[str, str] = None,
    ) -> list[str]:
        """
        全シナリオのアクティビティ図を個別ファイルとして保存する。

        Args:
            scenarios: 操作シナリオ一覧
            output_dir: 出力ディレクトリ（Path）
            uc_actor_map: ユースケースID → アクター名のマップ

        Returns:
            list[str]: 保存されたファイルパスの一覧
        """
        from pathlib import Path

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_files: list[str] = []

        # 全シナリオ概要図
        overview = self.generate_all_scenarios_flowchart(scenarios)
        overview_path = output_dir / "scenarios_overview.md"
        overview_path.write_text(
            f"# 操作シナリオ一覧\n\n```mermaid\n{overview}\n```\n",
            encoding="utf-8"
        )
        saved_files.append(str(overview_path))

        # 個別シナリオ図（最大50件）
        uc_actor_map = uc_actor_map or {}
        for sc in scenarios[:50]:
            actor_name = uc_actor_map.get(sc.usecase_id, "")
            seq_diagram = self.generate_sequence_diagram(sc, actor_name=actor_name)
            safe_id = sc.scenario_id.replace("-", "_")
            file_path = output_dir / f"scenario_{safe_id}.md"

            content = f"""# {sc.scenario_id}: {sc.scenario_name}

**ユースケース**: {sc.usecase_id} - {sc.usecase_name}
**シナリオ種別**: {sc.scenario_type}
**フロントエンドURL**: {sc.frontend_url or '未定義'}
**APIエンドポイント**: {sc.api_endpoint or '未定義'}

## シーケンス図

```mermaid
{seq_diagram}
```

## 操作ステップ

| # | アクター | アクション | 期待結果 |
|---|---------|-----------|---------|
"""
            for step in sc.steps:
                content += (
                    f"| {step.step_no} | {step.actor} | "
                    f"{step.action} | {step.expected_result} |\n"
                )

            if sc.variations:
                content += "\n## バリエーション\n\n"
                for v in sc.variations:
                    content += f"- {v}\n"

            file_path.write_text(content, encoding="utf-8")
            saved_files.append(str(file_path))

        return saved_files
