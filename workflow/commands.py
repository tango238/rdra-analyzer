"""業務フローのコマンド（guard 付き・純粋関数）。sync #5。

由来: workflows.md（ステップ）/ code/types/workflow.py（Phase 10）。

各コマンドは (現状態, 入力, now) → Result<Event, Error>。I/O は持たない
（イベント永続化・UC 読込・loop-e2e 送信は CLI 側＝境界）。不変条件を guard で守る:
- 承認・FB・編集・レビューは PdM のみ
- 承認は ReviewingFlow のみ／引き渡しは ApprovedFlow のみ（因果整合）
"""

from __future__ import annotations

from typing import Iterable, Optional

from .errors import (
    IllegalTransition,
    NoConfirmedUsecases,
    NotApproved,
    NotPdM,
    UnknownUsecase,
)
from .events import (
    ApprovedFlowHandedOff,
    BusinessFlowApproved,
    BusinessFlowEdited,
    BusinessFlowFeedbackGiven,
    BusinessFlowProposed,
    BusinessFlowReProposed,
    BusinessFlowReviewed,
)
from .result import Err, Ok, Result
from .state import (
    ApprovedFlow,
    BusinessFlowState,
    NeedsRevisionFlow,
    ProposedFlow,
    ReviewingFlow,
    status_of,
)


def _propose(
    flow_id: str, uc_ids: tuple[str, ...], confirmed_uc_ids: set[str]
) -> Optional[object]:
    if not confirmed_uc_ids:
        return NoConfirmedUsecases()
    for uc in uc_ids:
        if uc not in confirmed_uc_ids:
            return UnknownUsecase(uc)
    return None


def propose_flow(
    flow_id: str,
    uc_ids: Iterable[str],
    confirmed_uc_ids: set[str],
    now: str,
) -> Result:
    uc_tuple = tuple(uc_ids)
    err = _propose(flow_id, uc_tuple, confirmed_uc_ids)
    if err is not None:
        return Err(err)
    return Ok(BusinessFlowProposed(flow_id, uc_tuple, now))


def review_flow(state: Optional[BusinessFlowState], actor: str, now: str) -> Result:
    if actor != "PdM":
        return Err(NotPdM(actor))
    if not isinstance(state, ProposedFlow):
        return Err(IllegalTransition(status_of(state), "review"))
    return Ok(BusinessFlowReviewed(state.flow_id, "PdM", now))


def give_feedback(
    state: Optional[BusinessFlowState], actor: str, feedback: str, now: str
) -> Result:
    if actor != "PdM":
        return Err(NotPdM(actor))
    if not isinstance(state, ReviewingFlow):
        return Err(IllegalTransition(status_of(state), "feedback"))
    return Ok(BusinessFlowFeedbackGiven(state.flow_id, "PdM", feedback, now))


def re_propose_flow(
    state: Optional[BusinessFlowState], confirmed_uc_ids: set[str], now: str
) -> Result:
    if not isinstance(state, NeedsRevisionFlow):
        return Err(IllegalTransition(status_of(state), "rePropose"))
    err = _propose(state.flow_id, state.uc_ids, confirmed_uc_ids)
    if err is not None:
        return Err(err)
    return Ok(BusinessFlowReProposed(state.flow_id, state.uc_ids, now))


def edit_flow(
    state: Optional[BusinessFlowState], actor: str, edits: str, now: str
) -> Result:
    if actor != "PdM":
        return Err(NotPdM(actor))
    if not isinstance(state, (ProposedFlow, ReviewingFlow, NeedsRevisionFlow)):
        return Err(IllegalTransition(status_of(state), "edit"))
    return Ok(BusinessFlowEdited(state.flow_id, "PdM", edits, now))


def approve_flow(state: Optional[BusinessFlowState], actor: str, now: str) -> Result:
    if actor != "PdM":
        return Err(NotPdM(actor))
    if not isinstance(state, ReviewingFlow):
        return Err(IllegalTransition(status_of(state), "approve"))
    return Ok(BusinessFlowApproved(state.flow_id, "PdM", now))


def hand_off(state: Optional[BusinessFlowState], now: str) -> Result:
    if not isinstance(state, ApprovedFlow):
        return Err(NotApproved(status_of(state)))
    return Ok(ApprovedFlowHandedOff(state.flow_id, now))
