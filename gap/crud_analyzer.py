"""
CRUDギャップ分析モジュール

情報モデルの各エンティティに対して、
パート1の操作シナリオに Create/Read/Update/Delete が存在するかを確認する。
不足しているCRUD操作をMarkdownテーブル形式で出力する。
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime

from rdra.information_model import Entity
from analyzer.scenario_builder import OperationScenario
from analyzer.usecase_extractor import Usecase
from analyzer.source_parser import ParsedRoute


@dataclass
class CrudGap:
    """不足しているCRUD操作"""
    entity_name: str        # エンティティ名（日本語）
    class_name: str         # クラス名
    operation: str          # "Create" | "Read" | "Update" | "Delete"
    reason: str             # 不足している理由
    suggestion: str         # 改善提案


@dataclass
class EntityCrudStatus:
    """エンティティのCRUDステータス"""
    entity_name: str        # エンティティ名（日本語）
    class_name: str         # クラス名
    # 各CRUD操作の存在確認
    has_create: bool = False
    has_read: bool = False
    has_update: bool = False
    has_delete: bool = False
    # 確認根拠（シナリオID・ルートパス）
    create_evidence: list[str] = field(default_factory=list)
    read_evidence: list[str] = field(default_factory=list)
    update_evidence: list[str] = field(default_factory=list)
    delete_evidence: list[str] = field(default_factory=list)

    @property
    def coverage_percentage(self) -> int:
        """CRUD網羅率（%）"""
        count = sum([self.has_create, self.has_read, self.has_update, self.has_delete])
        return count * 25

    @property
    def missing_operations(self) -> list[str]:
        """不足しているCRUD操作の一覧"""
        missing = []
        if not self.has_create:
            missing.append("Create")
        if not self.has_read:
            missing.append("Read")
        if not self.has_update:
            missing.append("Update")
        if not self.has_delete:
            missing.append("Delete")
        return missing


class CrudAnalyzer:
    """
    エンティティと操作シナリオのCRUDギャップを分析するクラス。

    分析方法:
    1. APIルートのHTTPメソッドからCRUD操作を判定
       - POST   → Create
       - GET    → Read
       - PUT/PATCH → Update
       - DELETE → Delete
    2. 操作シナリオのステップ・アクションテキストからもCRUD操作を検出
    3. エンティティ名とルート・シナリオのエンティティ名を照合
    """

    # HTTPメソッド → CRUD操作のマッピング
    HTTP_TO_CRUD = {
        "POST":   "Create",
        "GET":    "Read",
        "PUT":    "Update",
        "PATCH":  "Update",
        "DELETE": "Delete",
    }

    # シナリオアクションの日本語キーワード → CRUD操作のマッピング
    ACTION_KEYWORDS = {
        "Create": [
            "作成", "登録", "追加", "新規", "create", "add", "new", "insert", "store",
            "post", "submit", "保存"
        ],
        "Read": [
            "一覧", "表示", "取得", "検索", "参照", "確認", "閲覧",
            "read", "list", "view", "show", "get", "fetch", "index"
        ],
        "Update": [
            "更新", "編集", "変更", "修正", "保存", "put", "patch",
            "update", "edit", "modify", "change"
        ],
        "Delete": [
            "削除", "除去", "delete", "remove", "destroy", "drop"
        ],
    }

    def __init__(self):
        pass

    def analyze(
        self,
        entities: list[Entity],
        routes: list[ParsedRoute],
        scenarios: list[OperationScenario],
        usecases: list[Usecase],
    ) -> tuple[list[EntityCrudStatus], list[CrudGap]]:
        """
        エンティティごとにCRUDギャップを分析する。

        Args:
            entities: 情報モデルのエンティティ一覧
            routes: 解析済みAPIルート一覧
            scenarios: 操作シナリオ一覧
            usecases: ユースケース一覧

        Returns:
            tuple[list[EntityCrudStatus], list[CrudGap]]:
                (CRUDステータス一覧, ギャップ一覧)
        """
        statuses: list[EntityCrudStatus] = []

        for entity in entities:
            status = self._analyze_entity(entity, routes, scenarios, usecases)
            statuses.append(status)

        # ギャップを抽出
        gaps = self._extract_gaps(statuses)

        return statuses, gaps

    def _analyze_entity(
        self,
        entity: Entity,
        routes: list[ParsedRoute],
        scenarios: list[OperationScenario],
        usecases: list[Usecase],
    ) -> EntityCrudStatus:
        """1エンティティのCRUDステータスを分析する"""
        status = EntityCrudStatus(
            entity_name=entity.name,
            class_name=entity.class_name,
        )

        # ルートからCRUD操作を検出
        self._check_routes(status, entity, routes)

        # 操作シナリオからCRUD操作を検出
        self._check_scenarios(status, entity, scenarios)

        # ユースケースからCRUD操作を検出
        self._check_usecases(status, entity, usecases)

        return status

    def _check_routes(
        self,
        status: EntityCrudStatus,
        entity: Entity,
        routes: list[ParsedRoute],
    ) -> None:
        """
        APIルートからエンティティのCRUD操作を検出する。

        エンティティのクラス名をスネークケースに変換してルートパスと照合する。
        例: BookingPlan → booking-plan, booking_plan, booking-plans
        """
        # エンティティ名のバリエーションを生成
        entity_patterns = self._entity_name_patterns(entity.class_name)

        for route in routes:
            # ルートパスにエンティティ名が含まれるかチェック
            path_lower = route.path.lower()
            if not any(pat in path_lower for pat in entity_patterns):
                continue

            crud_op = self.HTTP_TO_CRUD.get(route.method.upper())
            if not crud_op:
                continue

            evidence = f"{route.method} {route.path}"

            if crud_op == "Create" and not status.has_create:
                status.has_create = True
                status.create_evidence.append(evidence)
            elif crud_op == "Read" and not status.has_read:
                status.has_read = True
                status.read_evidence.append(evidence)
            elif crud_op == "Update" and not status.has_update:
                status.has_update = True
                status.update_evidence.append(evidence)
            elif crud_op == "Delete" and not status.has_delete:
                status.has_delete = True
                status.delete_evidence.append(evidence)

    def _check_scenarios(
        self,
        status: EntityCrudStatus,
        entity: Entity,
        scenarios: list[OperationScenario],
    ) -> None:
        """操作シナリオからエンティティのCRUD操作を検出する"""
        entity_patterns = self._entity_name_patterns(entity.class_name)
        entity_jp = entity.name

        for sc in scenarios:
            # シナリオが対象エンティティに関連するかチェック
            sc_text = (
                sc.usecase_name + " " +
                sc.scenario_name + " " +
                " ".join(step.action for step in sc.steps)
            ).lower()

            # エンティティ名（日本語・英語）のいずれかが含まれるか確認
            is_related = (
                any(pat in sc_text for pat in entity_patterns) or
                entity_jp in sc_text
            )
            if not is_related:
                continue

            # アクションテキストからCRUD操作を検出
            for operation, keywords in self.ACTION_KEYWORDS.items():
                if any(kw in sc_text for kw in keywords):
                    evidence = f"{sc.scenario_id}: {sc.scenario_name}"
                    if operation == "Create" and not status.has_create:
                        status.has_create = True
                        status.create_evidence.append(evidence)
                    elif operation == "Read" and not status.has_read:
                        status.has_read = True
                        status.read_evidence.append(evidence)
                    elif operation == "Update" and not status.has_update:
                        status.has_update = True
                        status.update_evidence.append(evidence)
                    elif operation == "Delete" and not status.has_delete:
                        status.has_delete = True
                        status.delete_evidence.append(evidence)

    def _check_usecases(
        self,
        status: EntityCrudStatus,
        entity: Entity,
        usecases: list[Usecase],
    ) -> None:
        """ユースケースからエンティティのCRUD操作を検出する"""
        entity_patterns = self._entity_name_patterns(entity.class_name)
        entity_jp = entity.name

        for uc in usecases:
            # ユースケースが対象エンティティに関連するかチェック
            related_entities_lower = [e.lower() for e in uc.related_entities]
            if entity.class_name not in uc.related_entities and \
               entity_jp not in uc.name and \
               not any(pat in uc.name.lower() for pat in entity_patterns):
                # 関連エンティティリストも確認
                if not any(
                    entity.class_name.lower() in e.lower()
                    for e in uc.related_entities
                ):
                    continue

            # ルートのHTTPメソッドからCRUD操作を判定
            for route_str in uc.related_routes:
                parts = route_str.split()
                if len(parts) >= 1:
                    method = parts[0].upper()
                    crud_op = self.HTTP_TO_CRUD.get(method)
                    evidence = f"{uc.id}: {uc.name} ({route_str})"

                    if crud_op == "Create" and not status.has_create:
                        status.has_create = True
                        status.create_evidence.append(evidence)
                    elif crud_op == "Read" and not status.has_read:
                        status.has_read = True
                        status.read_evidence.append(evidence)
                    elif crud_op == "Update" and not status.has_update:
                        status.has_update = True
                        status.update_evidence.append(evidence)
                    elif crud_op == "Delete" and not status.has_delete:
                        status.has_delete = True
                        status.delete_evidence.append(evidence)

    def _entity_name_patterns(self, class_name: str) -> list[str]:
        """
        クラス名から検索パターンのバリエーションを生成する。

        例: BookingPlan →
          ["booking_plan", "booking-plan", "booking_plans", "booking-plans",
           "bookingplan", "bookingplans"]
        """
        # キャメルケースをスネークケースに変換
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', class_name).lower()
        kebab = snake.replace("_", "-")
        lower = class_name.lower()

        patterns = [
            snake,
            kebab,
            lower,
            snake + "s",        # 複数形
            kebab + "s",        # 複数形（ケバブ）
            lower + "s",        # 複数形
        ]
        return patterns

    def _extract_gaps(
        self, statuses: list[EntityCrudStatus]
    ) -> list[CrudGap]:
        """CRUDステータスから不足操作のギャップを抽出する"""
        gaps: list[CrudGap] = []

        for status in statuses:
            for operation in status.missing_operations:
                suggestion = self._suggest_fix(status.class_name, operation)
                gaps.append(CrudGap(
                    entity_name=status.entity_name,
                    class_name=status.class_name,
                    operation=operation,
                    reason=f"{status.class_name}に対する{operation}操作のシナリオが未定義",
                    suggestion=suggestion,
                ))

        return gaps

    def _suggest_fix(self, class_name: str, operation: str) -> str:
        """不足CRUD操作に対する改善提案を生成する"""
        suggestions = {
            "Create": (
                f"{class_name}の新規作成機能とAPIエンドポイント（POST）を実装する。"
            ),
            "Read": (
                f"{class_name}の一覧・詳細取得APIエンドポイント（GET）を実装する。"
            ),
            "Update": (
                f"{class_name}の更新機能とAPIエンドポイント（PUT/PATCH）を実装する。"
            ),
            "Delete": (
                f"{class_name}の削除機能とAPIエンドポイント（DELETE）を実装する。"
            ),
        }
        return suggestions.get(operation, f"{operation}操作の実装を検討する")

    def save_to_markdown(
        self,
        statuses: list[EntityCrudStatus],
        gaps: list[CrudGap],
        output_path: Path,
    ) -> None:
        """
        分析結果をMarkdownテーブル形式で保存する。

        Args:
            statuses: エンティティのCRUDステータス一覧
            gaps: ギャップ一覧
            output_path: 出力ファイルパス
        """
        # カバレッジ計算
        total_entities = len(statuses)
        full_crud_entities = sum(
            1 for s in statuses if s.coverage_percentage == 100
        )
        avg_coverage = (
            sum(s.coverage_percentage for s in statuses) / total_entities
            if total_entities > 0 else 0
        )

        content = f"""# CRUDギャップ分析レポート

**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## サマリー

| 項目 | 値 |
|-----|---|
| 分析対象エンティティ数 | {total_entities} |
| CRUD完全網羅エンティティ | {full_crud_entities} |
| 平均CRUD網羅率 | {avg_coverage:.1f}% |
| ギャップ総数 | {len(gaps)} |

## エンティティ別CRUDステータス

| エンティティ | Create | Read | Update | Delete | 網羅率 |
|------------|--------|------|--------|--------|--------|
"""
        for status in sorted(statuses, key=lambda s: s.coverage_percentage):
            create_cell = "✅" if status.has_create else "❌"
            read_cell = "✅" if status.has_read else "❌"
            update_cell = "✅" if status.has_update else "❌"
            delete_cell = "✅" if status.has_delete else "❌"
            coverage = f"{status.coverage_percentage}%"
            content += (
                f"| {status.entity_name}（{status.class_name}）"
                f" | {create_cell} | {read_cell} | {update_cell} | {delete_cell}"
                f" | {coverage} |\n"
            )

        content += f"""
## 不足CRUD操作一覧（ギャップ）

| # | エンティティ | 不足操作 | 理由 | 改善提案 |
|---|------------|---------|------|---------|
"""
        for i, gap in enumerate(gaps, start=1):
            content += (
                f"| {i} | {gap.entity_name}（{gap.class_name}）"
                f" | {gap.operation} | {gap.reason} | {gap.suggestion} |\n"
            )

        content += "\n## 操作証跡詳細\n\n"
        for status in statuses:
            content += f"### {status.entity_name}（{status.class_name}）\n\n"
            content += f"**CRUD網羅率**: {status.coverage_percentage}%\n\n"

            if status.create_evidence:
                content += f"**Create証跡**: {'; '.join(status.create_evidence[:3])}\n\n"
            if status.read_evidence:
                content += f"**Read証跡**: {'; '.join(status.read_evidence[:3])}\n\n"
            if status.update_evidence:
                content += f"**Update証跡**: {'; '.join(status.update_evidence[:3])}\n\n"
            if status.delete_evidence:
                content += f"**Delete証跡**: {'; '.join(status.delete_evidence[:3])}\n\n"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
