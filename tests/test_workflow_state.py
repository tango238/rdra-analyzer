"""業務フロー状態機械（Event Sourcing の fold）のテスト — sync #5。

状態は保存せず、イベント列を fold して復元する（ES）。fold は純粋関数なので
I/O 無しでテストできる。
"""

from workflow.events import (
    ApprovedFlowHandedOff,
    BusinessFlowApproved,
    BusinessFlowFeedbackGiven,
    BusinessFlowProposed,
    BusinessFlowReProposed,
    BusinessFlowReviewed,
)
from workflow.state import (
    ApprovedFlow,
    HandedOffFlow,
    NeedsRevisionFlow,
    ProposedFlow,
    ReviewingFlow,
    fold,
)


def test_fold_empty_is_none() -> None:
    assert fold([]) is None


def test_fold_proposed() -> None:
    s = fold([BusinessFlowProposed("BF-1", ("UC-001",), "t0")])
    assert isinstance(s, ProposedFlow)
    assert s.flow_id == "BF-1"
    assert s.uc_ids == ("UC-001",)


def test_fold_reviewed() -> None:
    s = fold([
        BusinessFlowProposed("BF-1", ("UC-001",), "t0"),
        BusinessFlowReviewed("BF-1", "PdM", "t1"),
    ])
    assert isinstance(s, ReviewingFlow)


def test_fold_feedback_to_needs_revision() -> None:
    s = fold([
        BusinessFlowProposed("BF-1", ("UC-001",), "t0"),
        BusinessFlowReviewed("BF-1", "PdM", "t1"),
        BusinessFlowFeedbackGiven("BF-1", "PdM", "ステップ3が不足", "t2"),
    ])
    assert isinstance(s, NeedsRevisionFlow)
    assert s.feedback_history == ("ステップ3が不足",)


def test_fold_repropose_back_to_proposed() -> None:
    s = fold([
        BusinessFlowProposed("BF-1", ("UC-001",), "t0"),
        BusinessFlowReviewed("BF-1", "PdM", "t1"),
        BusinessFlowFeedbackGiven("BF-1", "PdM", "FB", "t2"),
        BusinessFlowReProposed("BF-1", ("UC-001", "UC-002"), "t3"),
    ])
    assert isinstance(s, ProposedFlow)
    assert s.uc_ids == ("UC-001", "UC-002")


def test_fold_full_lifecycle_to_handoff() -> None:
    s = fold([
        BusinessFlowProposed("BF-1", ("UC-001",), "t0"),
        BusinessFlowReviewed("BF-1", "PdM", "t1"),
        BusinessFlowApproved("BF-1", "PdM", "t2"),
        ApprovedFlowHandedOff("BF-1", "t3"),
    ])
    assert isinstance(s, HandedOffFlow)


def test_fold_approved_records_approver() -> None:
    s = fold([
        BusinessFlowProposed("BF-1", ("UC-001",), "t0"),
        BusinessFlowReviewed("BF-1", "PdM", "t1"),
        BusinessFlowApproved("BF-1", "PdM", "t2"),
    ])
    assert isinstance(s, ApprovedFlow)
    assert s.approver == "PdM"
