"""救済フロー（静的棄却UC ＋ loop-e2e実績 → 再昇格）のテスト — sync #1 follow-on。

discovery の調停ルール:「静的で棄却 ＋ loop-e2e に実績あり → 救済（実績由来確定）」。
棄却UCはコード証拠アンカーが空なのでルート照合できない。救済は**名前一致**で行い、
実績由来の証拠（facts）を付与して confidence=derived で確定に再昇格する。
"""

from reconciliation.reconcile import reconcile
from extraction.rejection_log import RejectedUsecase


def _pending(scenario_name: str):
    return {"pending": [{
        "loop_e2e_id": "le-1",
        "scenario_name": scenario_name,
        "api_endpoints": [{"method": "POST", "path": "/api/stock/adjust"}],
        "steps": [{"actor": "管理者", "action": "在庫調整"}],
    }]}


_CHECKPOINT = {
    "routes": [{"method": "POST", "path": "/api/stock/adjust", "controller": "StockController"}],
    "pages": [],
}


def test_rescue_rejected_uc_by_name() -> None:
    analysis = {"usecases": []}  # 確定UCなし
    rejected = [RejectedUsecase(id="UC-007", name="在庫を調整する", reason="証拠なし", missing_evidence=["related_routes"])]
    result = reconcile(analysis, _pending("在庫を調整する"), _CHECKPOINT, rejected=rejected)

    assert result.created == 0          # 新規ではなく
    assert len(result.rescued) == 1     # 救済された
    r = result.rescued[0]
    assert r.id == "UC-007"             # 棄却UCの id を保持
    assert r.confidence == "derived"    # 実績由来
    assert "POST /api/stock/adjust" in r.related_routes  # 実績の証拠を付与


def test_no_rescue_when_name_differs_falls_back_to_synthesize() -> None:
    analysis = {"usecases": []}
    rejected = [RejectedUsecase(id="UC-007", name="全く別のUC", reason="x", missing_evidence=[])]
    result = reconcile(analysis, _pending("在庫を調整する"), _CHECKPOINT, rejected=rejected)

    assert result.rescued == []
    assert result.created == 1          # 従来通り新規 UC-LE
    assert result.new_usecases[0].confidence == "inferred"


def test_rescue_pool_default_empty_preserves_existing_behavior() -> None:
    analysis = {"usecases": []}
    result = reconcile(analysis, _pending("在庫を調整する"), _CHECKPOINT)  # rejected 省略
    assert result.rescued == []
    assert result.created == 1
