"""
ユースケース複合図生成モジュール

RDRA のユースケース複合図を Mermaid の flowchart/graph 記法で生成する。
アクター・ユースケース・条件・バリエーションを表現する。
"""

from dataclasses import dataclass
from analyzer.usecase_extractor import Usecase
from llm.provider import LLMProvider


class UsecaseDiagramGenerator:
    """
    ユースケース一覧から RDRA ユースケース複合図を生成するクラス。

    RDRA のユースケース複合図では以下を表現する:
    - アクター（外部環境）
    - ユースケース（システムが提供する価値）
    - 条件（ユースケースの適用条件）
    - バリエーション（ユースケースのバリエーション）
    """

    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider

    def generate_mermaid(self, usecases: list[Usecase]) -> str:
        """
        ユースケース一覧から Mermaid flowchart を生成する。

        カテゴリごとにサブグラフとしてグループ化する。

        Args:
            usecases: 抽出済みユースケース一覧

        Returns:
            str: Mermaid flowchart 記法の文字列
        """
        lines = [
            "---",
            "title: ユースケース複合図",
            "---",
            "flowchart LR",
        ]

        # アクターをノードとして定義（左辺）
        actors = sorted(set(uc.actor for uc in usecases))
        lines.append("")
        lines.append("    %% アクター（外部環境）")
        for actor in actors:
            safe_id = actor.replace(" ", "_").replace("-", "_")
            lines.append(f'    {safe_id}(["👤 {actor}"])')
        lines.append("")

        # カテゴリ別にユースケースをグループ化
        categories: dict[str, list[Usecase]] = {}
        for uc in usecases:
            categories.setdefault(uc.category, []).append(uc)

        lines.append("    %% ユースケース（カテゴリ別）")
        for category, cat_usecases in categories.items():
            safe_cat = category.replace(" ", "_").replace("-", "_").replace("・", "_")
            lines.append(f'    subgraph SG_{safe_cat}["{category}"]')

            for uc in cat_usecases:
                uc_id = uc.id.replace("-", "_")
                priority_icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    uc.priority, "🟡"
                )
                lines.append(
                    f'        {uc_id}["{priority_icon} {uc.id}\\n{uc.name}"]'
                )

            lines.append("    end")
            lines.append("")

        # アクター→ユースケースのエッジ
        lines.append("    %% アクターとユースケースの関係")
        for uc in usecases:
            actor_id = uc.actor.replace(" ", "_").replace("-", "_")
            uc_id = uc.id.replace("-", "_")
            lines.append(f"    {actor_id} --> {uc_id}")

        # スタイル定義
        lines.append("")
        lines.append("    %% スタイル")
        lines.append("    classDef actor fill:#e8f4fd,stroke:#2196F3,stroke-width:2px")
        lines.append("    classDef usecase fill:#fff3e0,stroke:#FF9800")
        lines.append("    classDef high fill:#ffebee,stroke:#F44336")
        for actor in actors:
            safe_id = actor.replace(" ", "_").replace("-", "_")
            lines.append(f"    class {safe_id} actor")
        for uc in usecases:
            uc_id = uc.id.replace("-", "_")
            if uc.priority == "high":
                lines.append(f"    class {uc_id} high")
            else:
                lines.append(f"    class {uc_id} usecase")

        return "\n".join(lines)

    def generate_conditions_mermaid(self, usecases: list[Usecase]) -> str:
        """
        条件・バリエーション付きのユースケース詳細図を生成する。

        各ユースケースに対して事前条件・事後条件をノードで表現する。

        Args:
            usecases: 抽出済みユースケース一覧

        Returns:
            str: Mermaid flowchart の文字列（条件付き）
        """
        lines = [
            "---",
            "title: ユースケース複合図（条件・バリエーション付き）",
            "---",
            "flowchart TD",
        ]

        # 最大20件を表示（図が大きくなりすぎるため）
        target_usecases = usecases[:20]

        for uc in target_usecases:
            uc_id = uc.id.replace("-", "_")
            lines.append(f"")
            lines.append(f"    %% === {uc.id}: {uc.name} ===")

            # ユースケースノード
            lines.append(
                f'    {uc_id}["{uc.id}\\n{uc.name}\\nアクター: {uc.actor}"]'
            )

            # 事前条件
            for i, pre in enumerate(uc.preconditions[:3]):
                cond_id = f"{uc_id}_pre{i}"
                safe_pre = pre.replace('"', "'")
                lines.append(f'    {cond_id}{{"{safe_pre}"}}')
                lines.append(f"    {cond_id} --> {uc_id}")

            # 事後条件
            for i, post in enumerate(uc.postconditions[:2]):
                post_id = f"{uc_id}_post{i}"
                safe_post = post.replace('"', "'")
                lines.append(f'    {post_id}(["{safe_post}"])')
                lines.append(f"    {uc_id} --> {post_id}")

        lines.append("")
        lines.append("    classDef condition fill:#e3f2fd,stroke:#1565C0")
        lines.append("    classDef postcondition fill:#e8f5e9,stroke:#2E7D32")

        return "\n".join(lines)

    def generate_single_condition_mermaid(self, uc: Usecase) -> str:
        """単一ユースケースの条件図を生成する"""
        uc_id = uc.id.replace("-", "_")
        lines = ["flowchart TD"]
        lines.append(f'    {uc_id}["{uc.id}\\n{uc.name}\\nアクター: {uc.actor}"]')

        for i, pre in enumerate(uc.preconditions):
            cond_id = f"{uc_id}_pre{i}"
            safe_pre = pre.replace('"', "'")
            lines.append(f'    {cond_id}{{"{safe_pre}"}}')
            lines.append(f"    {cond_id} --> {uc_id}")

        for i, post in enumerate(uc.postconditions):
            post_id = f"{uc_id}_post{i}"
            safe_post = post.replace('"', "'")
            lines.append(f'    {post_id}(["{safe_post}"])')
            lines.append(f"    {uc_id} --> {post_id}")

        # 関連エンティティ
        for i, ent in enumerate(uc.related_entities[:5]):
            ent_id = f"{uc_id}_ent{i}"
            lines.append(f'    {ent_id}[/"{ent}"\\]')
            lines.append(f"    {uc_id} -.-> {ent_id}")

        lines.append("    classDef condition fill:#e3f2fd,stroke:#1565C0")
        lines.append("    classDef postcondition fill:#e8f5e9,stroke:#2E7D32")
        return "\n".join(lines)
