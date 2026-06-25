"""業務フローのコマンド（guard 付き）のテスト — sync #5。

コマンドは純粋関数 (state, 入力, now) → Result<Event, Error>。
不変条件（PdM のみ承認・承認後のみ引き渡し・正しい状態遷移）を guard で守る。
"""

from workflow.commands import (
    approve_flow,
    give_feedback,
    hand_off,
    propose_flow,
    review_flow,
)
from workflow.errors import (
    IllegalTransition,
    NoConfirmedUsecases,
    NotApproved,
    NotPdM,
    UnknownUsecase,
)
from workflow.events import (
    ApprovedFlowHandedOff,
    BusinessFlowApproved,
    BusinessFlowProposed,
)
from workflow.result import Err, Ok
from workflow.state import ApprovedFlow, ProposedFlow, ReviewingFlow, fold


class TestPropose:
    def test_no_confirmed_usecases(self) -> None:
        r = propose_flow("BF-1", ("UC-001",), confirmed_uc_ids=set(), now="t0")
        assert isinstance(r, Err) and isinstance(r.error, NoConfirmedUsecases)

    def test_unknown_usecase(self) -> None:
        r = propose_flow("BF-1", ("UC-999",), confirmed_uc_ids={"UC-001"}, now="t0")
        assert isinstance(r, Err) and isinstance(r.error, UnknownUsecase)
        assert r.error.uc_id == "UC-999"

    def test_ok(self) -> None:
        r = propose_flow("BF-1", ("UC-001",), confirmed_uc_ids={"UC-001"}, now="t0")
        assert isinstance(r, Ok) and isinstance(r.value, BusinessFlowProposed)
        assert r.value.uc_ids == ("UC-001",)


class TestApprove:
    def _reviewing(self) -> ReviewingFlow:
        return ReviewingFlow("BF-1", ("UC-001",))

    def test_pdm_from_reviewing_ok(self) -> None:
        r = approve_flow(self._reviewing(), actor="PdM", now="t2")
        assert isinstance(r, Ok) and isinstance(r.value, BusinessFlowApproved)
        assert r.value.approver == "PdM"

    def test_non_pdm_rejected(self) -> None:
        r = approve_flow(self._reviewing(), actor="System", now="t2")
        assert isinstance(r, Err) and isinstance(r.error, NotPdM)

    def test_wrong_state_rejected(self) -> None:
        r = approve_flow(ProposedFlow("BF-1", ("UC-001",)), actor="PdM", now="t2")
        assert isinstance(r, Err) and isinstance(r.error, IllegalTransition)


class TestReviewAndFeedback:
    def test_review_from_proposed_ok(self) -> None:
        r = review_flow(ProposedFlow("BF-1", ("UC-001",)), actor="PdM", now="t1")
        assert isinstance(r, Ok)

    def test_review_wrong_state(self) -> None:
        r = review_flow(ReviewingFlow("BF-1", ("UC-001",)), actor="PdM", now="t1")
        assert isinstance(r, Err) and isinstance(r.error, IllegalTransition)

    def test_feedback_non_pdm_rejected(self) -> None:
        r = give_feedback(ReviewingFlow("BF-1", ("UC-001",)), actor="System", feedback="x", now="t2")
        assert isinstance(r, Err) and isinstance(r.error, NotPdM)


class TestHandOff:
    def test_from_approved_ok(self) -> None:
        r = hand_off(ApprovedFlow("BF-1", ("UC-001",)), now="t3")
        assert isinstance(r, Ok) and isinstance(r.value, ApprovedFlowHandedOff)

    def test_not_approved_rejected(self) -> None:
        r = hand_off(ReviewingFlow("BF-1", ("UC-001",)), now="t3")
        assert isinstance(r, Err) and isinstance(r.error, NotApproved)


class TestHappyPathChained:
    def test_propose_review_approve_handoff(self) -> None:
        events = []
        r1 = propose_flow("BF-1", ("UC-001",), confirmed_uc_ids={"UC-001"}, now="t0")
        events.append(r1.value)
        r2 = review_flow(fold(events), actor="PdM", now="t1")
        events.append(r2.value)
        r3 = approve_flow(fold(events), actor="PdM", now="t2")
        events.append(r3.value)
        r4 = hand_off(fold(events), now="t3")
        events.append(r4.value)
        final = fold(events)
        assert final.kind == "handed_off"
