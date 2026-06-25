"""Precision 棄却 ＋ 棄却ログ のテスト — sync 差異 #1。

証拠の連鎖が切れる（コード証拠アンカーが一切ない）UC を確定モデルから除外し、
棄却ログへ退避する。棄却＝破棄ではなく、理由＋欠落証拠を記録する。
"""

from analyzer.rejection_log import (
    RejectedUsecase,
    has_code_evidence,
    load_rejected,
    missing_evidence,
    partition_usecases,
    rejected_to_dict,
)
from analyzer.usecase_extractor import Usecase


def _uc(uc_id: str = "UC-001", **kw) -> Usecase:
    base = dict(
        id=uc_id,
        name="商品を登録する",
        actor="管理者",
        description="",
        preconditions=[],
        postconditions=[],
        related_routes=[],
        related_pages=[],
        related_entities=[],
        category="商品管理",
    )
    base.update(kw)
    return Usecase(**base)  # type: ignore[arg-type]


class TestEvidence:
    def test_has_code_evidence_true_when_any_anchor_present(self) -> None:
        assert has_code_evidence(_uc(related_routes=["POST /products"]))
        assert has_code_evidence(_uc(related_controllers=["ProductController"]))
        assert has_code_evidence(_uc(related_entities=["Product"]))
        assert has_code_evidence(_uc(related_pages=["/products/new"]))

    def test_has_code_evidence_false_when_all_anchors_empty(self) -> None:
        assert not has_code_evidence(_uc())

    def test_missing_evidence_lists_empty_anchor_fields(self) -> None:
        uc = _uc(related_routes=["POST /products"], related_entities=["Product"])
        miss = missing_evidence(uc)
        assert "related_controllers" in miss
        assert "related_pages" in miss
        assert "related_routes" not in miss
        assert "related_entities" not in miss


class TestPartition:
    def test_splits_confirmed_and_rejected(self) -> None:
        confirmed_uc = _uc("UC-001", related_routes=["GET /a"])
        hallucinated = _uc("UC-002")
        confirmed, rejected = partition_usecases([confirmed_uc, hallucinated])
        assert [u.id for u in confirmed] == ["UC-001"]
        assert [r.id for r in rejected] == ["UC-002"]
        assert isinstance(rejected[0], RejectedUsecase)
        assert rejected[0].reason
        assert rejected[0].missing_evidence

    def test_does_not_mutate_input(self) -> None:
        ucs = [_uc("UC-001", related_routes=["GET /a"]), _uc("UC-002")]
        partition_usecases(ucs)
        assert len(ucs) == 2
        assert [u.id for u in ucs] == ["UC-001", "UC-002"]

    def test_all_confirmed_when_every_uc_has_evidence(self) -> None:
        ucs = [_uc("UC-001", related_routes=["GET /a"]), _uc("UC-002", related_entities=["B"])]
        confirmed, rejected = partition_usecases(ucs)
        assert len(confirmed) == 2
        assert rejected == []


class TestSerialization:
    def test_rejected_roundtrip(self) -> None:
        _, rejected = partition_usecases([_uc("UC-009", name="幽霊UC")])
        dicts = [rejected_to_dict(r) for r in rejected]
        loaded = load_rejected({"rejected": dicts})
        assert loaded[0].id == "UC-009"
        assert loaded[0].name == "幽霊UC"
        assert loaded[0].missing_evidence == rejected[0].missing_evidence

    def test_load_legacy_missing_fields(self) -> None:
        loaded = load_rejected({"rejected": [{"id": "UC-009"}]})
        assert loaded[0].id == "UC-009"
        assert loaded[0].missing_evidence == []
