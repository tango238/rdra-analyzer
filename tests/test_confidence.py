"""確度ラベル (confidence) のテスト — sync 差異 #2。

確定層（コード証拠）= confirmed / 派生層（決定的導出）= derived /
合成・LLM 推論 = inferred の三値を、抽出物に付与・永続化できることを検証する。
"""

from analyzer.reconcile import (
    PendingEntry,
    ReconcileFacts,
    _load_usecases,
    _synthesize_usecase,
    _usecase_to_dict,
)
from analyzer.source_parser import EntityOperation
from analyzer.usecase_extractor import Usecase
from confidence import coerce, rank


def _uc(**kw) -> Usecase:
    base = dict(
        id="UC-001",
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


class TestConfidenceType:
    def test_rank_orders_confirmed_above_derived_above_inferred(self) -> None:
        assert rank("confirmed") > rank("derived") > rank("inferred")

    def test_coerce_passes_through_valid_values(self) -> None:
        assert coerce("derived") == "derived"

    def test_coerce_falls_back_to_default_for_unknown(self) -> None:
        assert coerce(None) == "confirmed"
        assert coerce("bogus") == "confirmed"
        assert coerce("bogus", default="inferred") == "inferred"


class TestUsecaseConfidence:
    def test_default_is_confirmed(self) -> None:
        assert _uc().confidence == "confirmed"

    def test_roundtrip_preserves_confidence(self) -> None:
        uc = _uc(confidence="inferred")
        loaded = _load_usecases({"usecases": [_usecase_to_dict(uc)]})
        assert loaded[0].confidence == "inferred"

    def test_load_legacy_dict_without_confidence_defaults_confirmed(self) -> None:
        legacy = {"id": "UC-009", "name": "旧UC", "actor": "ユーザー"}
        loaded = _load_usecases({"usecases": [legacy]})
        assert loaded[0].confidence == "confirmed"


class TestEntityOperationConfidence:
    def test_default_is_confirmed(self) -> None:
        op = EntityOperation(
            entity_class="Stock",
            operation="Update",
            method_signature="Stock::decrement('qty')",
            source_file="app/Services/OrderService.php",
            source_class="OrderService",
            source_method="createOrder",
        )
        assert op.confidence == "confirmed"


class TestSynthesizedUsecaseIsInferred:
    def test_reconcile_synthesized_uc_is_inferred(self) -> None:
        entry = PendingEntry(loop_e2e_id="login-flow", scenario_name="ログイン")
        facts = ReconcileFacts()
        uc = _synthesize_usecase(entry, facts, counter=1)
        assert uc.id == "UC-LE-001"
        assert uc.confidence == "inferred"
