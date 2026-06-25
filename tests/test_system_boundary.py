"""システム境界図生成のテスト — sync 差異 #3。

接点（画面）× 起点（API エンドポイント）の対応からシステム境界を描く。
enrich の照合結果（related_pages/related_views/related_routes）から決定的に生成する（LLM 不要）。
"""

import re

from extraction.usecase_extractor import UseCase
from extraction.derived.system_boundary import SystemBoundaryGenerator


def _uc(**kw) -> UseCase:
    base = dict(
        id="UC-001",
        name="注文を確定する",
        actor="管理者",
        description="",
        preconditions=[],
        postconditions=[],
        related_routes=["POST /api/orders"],
        related_pages=["/orders/new"],
        related_entities=["Order"],
        category="注文管理",
    )
    base.update(kw)
    return UseCase(**base)  # type: ignore[arg-type]


class TestSystemBoundary:
    def test_emits_flowchart_with_boundary_subgraph(self) -> None:
        out = SystemBoundaryGenerator().generate_mermaid([_uc()])
        assert "flowchart" in out
        assert "システム境界" in out

    def test_actor_outside_screen_and_endpoint_inside(self) -> None:
        out = SystemBoundaryGenerator().generate_mermaid([_uc()])
        assert "管理者" in out          # アクター（境界の外）
        assert "/orders/new" in out      # 接点（画面）
        assert "POST /api/orders" in out  # 起点（エンドポイント）

    def test_connects_actor_to_screen_to_endpoint(self) -> None:
        out = SystemBoundaryGenerator().generate_mermaid([_uc()])
        # エッジが少なくとも2本（actor->screen, screen->endpoint）
        assert out.count("-->") >= 2

    def test_endpoint_direct_when_no_screen(self) -> None:
        out = SystemBoundaryGenerator().generate_mermaid(
            [_uc(related_pages=[], related_views=[])]
        )
        assert "POST /api/orders" in out
        assert "-->" in out  # actor -> endpoint 直結

    def test_empty_usecases_does_not_crash(self) -> None:
        out = SystemBoundaryGenerator().generate_mermaid([])
        assert "flowchart" in out

    def test_deterministic_same_input_same_output(self) -> None:
        gen = SystemBoundaryGenerator()
        ucs = [_uc(), _uc(id="UC-002", actor="一般ユーザー", related_routes=["GET /api/items"])]
        assert gen.generate_mermaid(ucs) == gen.generate_mermaid(ucs)

    def test_non_ascii_actors_get_distinct_node_ids(self) -> None:
        # 日本語アクター名は ASCII へ畳むと全消失し同一ノードに潰れていた（Codex P2）。
        ucs = [
            _uc(id="UC-001", actor="管理者", related_routes=["POST /api/orders"], related_pages=[]),
            _uc(id="UC-002", actor="一般ユーザー", related_routes=["GET /api/items"], related_pages=[]),
        ]
        out = SystemBoundaryGenerator().generate_mermaid(ucs)
        actor_ids = re.findall(r"class (\S+) actor", out)
        assert len(actor_ids) == 2
        assert len(set(actor_ids)) == 2  # 別アクターが同一ノードに衝突しない

    def test_non_ascii_screens_get_distinct_node_ids(self) -> None:
        ucs = [
            _uc(id="UC-001", actor="管理者", related_pages=["注文画面"], related_routes=["POST /api/orders"]),
            _uc(id="UC-002", actor="管理者", related_pages=["顧客画面"], related_routes=["GET /api/customers"]),
        ]
        out = SystemBoundaryGenerator().generate_mermaid(ucs)
        screen_ids = re.findall(r"class (\S+) screen", out)
        assert len(set(screen_ids)) == 2
