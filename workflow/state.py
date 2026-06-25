"""業務フローの状態機械 — OR 型 ＋ fold（Event Sourcing）。sync #5。

由来: aggregates.md（BusinessFlow Aggregate）/ workflows.md（ステージ＝状態型）/
code/types/states.py（Phase 10 型骨格）。

状態は保存せず fold(events) で復元する。各状態を別型にし、許される遷移だけを
commands.py の関数が受け取る（「不正状態を表現不能に」）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Union

from .events import (
    ApprovedFlowHandedOff,
    BusinessFlowApproved,
    BusinessFlowEdited,
    BusinessFlowEvent,
    BusinessFlowFeedbackGiven,
    BusinessFlowProposed,
    BusinessFlowReProposed,
    BusinessFlowReviewed,
    FlowId,
    UsecaseId,
)


@dataclass(frozen=True)
class ProposedFlow:
    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    kind: Literal["proposed"] = "proposed"


@dataclass(frozen=True)
class ReviewingFlow:
    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    kind: Literal["reviewing"] = "reviewing"


@dataclass(frozen=True)
class NeedsRevisionFlow:
    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    feedback_history: tuple[str, ...] = field(default_factory=tuple)
    kind: Literal["needs_revision"] = "needs_revision"


@dataclass(frozen=True)
class ApprovedFlow:
    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    approver: Literal["PdM"] = "PdM"
    kind: Literal["approved"] = "approved"


@dataclass(frozen=True)
class HandedOffFlow:
    flow_id: FlowId
    kind: Literal["handed_off"] = "handed_off"


BusinessFlowState = Union[
    ProposedFlow, ReviewingFlow, NeedsRevisionFlow, ApprovedFlow, HandedOffFlow
]


def status_of(state: Optional[BusinessFlowState]) -> str:
    return state.kind if state is not None else "none"


def apply(state: Optional[BusinessFlowState], ev: BusinessFlowEvent) -> BusinessFlowState:
    """1イベントを畳み込む。状態型を遷移させる。"""
    if isinstance(ev, BusinessFlowProposed):
        return ProposedFlow(ev.flow_id, ev.uc_ids)
    if isinstance(ev, BusinessFlowReProposed):
        return ProposedFlow(ev.flow_id, ev.uc_ids)
    if isinstance(ev, BusinessFlowReviewed):
        assert state is not None
        return ReviewingFlow(state.flow_id, state.uc_ids)
    if isinstance(ev, BusinessFlowFeedbackGiven):
        prev = state.feedback_history if isinstance(state, NeedsRevisionFlow) else ()
        assert state is not None
        return NeedsRevisionFlow(state.flow_id, state.uc_ids, (*prev, ev.feedback))
    if isinstance(ev, BusinessFlowEdited):
        assert state is not None
        return state  # 編集は状態型を変えない（uc_ids 等の中身変更は将来拡張）
    if isinstance(ev, BusinessFlowApproved):
        assert state is not None
        return ApprovedFlow(state.flow_id, state.uc_ids, approver=ev.approver)
    if isinstance(ev, ApprovedFlowHandedOff):
        assert state is not None
        return HandedOffFlow(state.flow_id)
    raise ValueError(f"unknown event: {ev!r}")


def fold(events: list[BusinessFlowEvent]) -> Optional[BusinessFlowState]:
    """イベント列を畳み込んで現在状態を得る（純粋）。空なら None。"""
    state: Optional[BusinessFlowState] = None
    for ev in events:
        state = apply(state, ev)
    return state
