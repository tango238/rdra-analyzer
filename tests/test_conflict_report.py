"""矛盾検出 ＋ 要調査フラグ のテスト — sync 差異 #4。

reconcile で既存 UC にマッチした実績が UC の宣言と食い違うとき、UC を上書きせず
（「コードを真」）矛盾を別レポートに「要調査」として記録する。
"""

from reconciliation.conflict_report import Conflict, conflict_to_dict, load_conflicts
from reconciliation.reconcile import PendingEntry, detect_conflicts, reconcile
from extraction.usecase_extractor import Usecase


def _uc(**kw) -> Usecase:
    base = dict(
        id="UC-001",
        name="注文を確定する",
        actor="管理者",
        description="",
        preconditions=[],
        postconditions=[],
        related_routes=["POST /api/orders"],
        related_pages=[],
        related_entities=[],
        category="注文管理",
        related_controllers=["OrderController"],
    )
    base.update(kw)
    return Usecase(**base)  # type: ignore[arg-type]


class TestActorMismatch:
    def test_flags_when_actor_differs(self) -> None:
        entry = PendingEntry(loop_e2e_id="x", steps=[{"actor": "ゲスト", "action": "a"}])
        conflicts = detect_conflicts(entry, _uc(), {})
        kinds = {c.kind for c in conflicts}
        assert "actor_mismatch" in kinds
        c = next(c for c in conflicts if c.kind == "actor_mismatch")
        assert c.code_value == "管理者"
        assert "ゲスト" in c.actual_value

    def test_no_flag_when_actor_matches(self) -> None:
        entry = PendingEntry(loop_e2e_id="x", steps=[{"actor": "管理者", "action": "a"}])
        conflicts = detect_conflicts(entry, _uc(), {})
        assert all(c.kind != "actor_mismatch" for c in conflicts)

    def test_no_flag_when_actor_unknown(self) -> None:
        entry = PendingEntry(loop_e2e_id="x", steps=[])
        assert detect_conflicts(entry, _uc(), {}) == []


class TestControllerMismatch:
    def test_flags_when_actual_controller_differs(self) -> None:
        # 実績は /api/payments を叩き PaymentController に解決するが、UC は OrderController を宣言
        checkpoint = {
            "routes": [{"method": "POST", "path": "/api/payments", "controller": "PaymentController"}],
            "pages": [],
        }
        entry = PendingEntry(
            loop_e2e_id="x",
            api_endpoints=[{"method": "POST", "path": "/api/payments"}],
            steps=[{"actor": "管理者"}],
        )
        conflicts = detect_conflicts(entry, _uc(), checkpoint)
        assert any(c.kind == "controller_mismatch" for c in conflicts)
        c = next(c for c in conflicts if c.kind == "controller_mismatch")
        assert "PaymentController" in c.actual_value
        assert "OrderController" in c.code_value

    def test_no_flag_when_controller_overlaps(self) -> None:
        checkpoint = {
            "routes": [{"method": "POST", "path": "/api/orders", "controller": "OrderController"}],
            "pages": [],
        }
        entry = PendingEntry(
            loop_e2e_id="x",
            api_endpoints=[{"method": "POST", "path": "/api/orders"}],
            steps=[{"actor": "管理者"}],
        )
        conflicts = detect_conflicts(entry, _uc(), checkpoint)
        assert all(c.kind != "controller_mismatch" for c in conflicts)


class TestSerialization:
    def test_roundtrip(self) -> None:
        c = Conflict(usecase_id="UC-001", kind="actor_mismatch",
                     detail="d", code_value="管理者", actual_value="ゲスト")
        loaded = load_conflicts({"conflicts": [conflict_to_dict(c)]})
        assert loaded[0] == c

    def test_load_legacy(self) -> None:
        loaded = load_conflicts({"conflicts": [{"usecase_id": "UC-001", "kind": "actor_mismatch"}]})
        assert loaded[0].usecase_id == "UC-001"
        assert loaded[0].detail == ""


class TestReconcileIntegration:
    def test_reconcile_records_conflicts_for_matched_uc(self) -> None:
        analysis = {"usecases": [{
            "id": "UC-001", "name": "注文", "actor": "管理者",
            "related_routes": ["POST /api/orders"],
        }]}
        pending = {"pending": [{
            "loop_e2e_id": "le-1",
            "api_endpoints": [{"method": "POST", "path": "/api/orders"}],
            "steps": [{"actor": "ゲスト", "action": "注文"}],
        }]}
        result = reconcile(analysis, pending, {})
        # 既存 UC にマッチ（新規生成ではない）
        assert result.created == 0
        assert result.linked == 1
        assert any(c.kind == "actor_mismatch" for c in result.conflicts)
