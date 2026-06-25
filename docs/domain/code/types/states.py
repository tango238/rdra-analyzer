"""業務フローの状態機械 — OR 型（判別可能ユニオン）。

由来: aggregates.md（BusinessFlow Aggregate）/ workflows.md（ステージ＝状態型）。

DMMF「不正状態を表現不能に」: 各状態を別の型にし、その状態で許される遷移だけを
別ファイル（workflow.py）の関数シグネチャが受け取る。例えば handOff は ApprovedFlow
しか受け取らない＝「未承認の引き渡し」が型レベルで不能。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Union

from .value_objects import FlowId, UsecaseId


@dataclass(frozen=True)
class ProposedFlow:
    """System が確定UC群から想定済み。uc_ids は全て confirmed UC。未レビュー。"""

    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    kind: Literal["proposed"] = "proposed"


@dataclass(frozen=True)
class ReviewingFlow:
    """PdM がレビュー着手済み。"""

    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    kind: Literal["reviewing"] = "reviewing"


@dataclass(frozen=True)
class NeedsRevisionFlow:
    """PdM が FB 済み。feedback_history に理由。System 再想定待ち。"""

    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    feedback_history: tuple[str, ...] = field(default_factory=tuple)
    kind: Literal["needs_revision"] = "needs_revision"


@dataclass(frozen=True)
class ApprovedFlow:
    """PdM 承認済み。approver 記録。handOff のみ可能。"""

    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    approver: Literal["PdM"]
    kind: Literal["approved"] = "approved"


@dataclass(frozen=True)
class HandedOffFlow:
    """loop-e2e へ引き渡し済み（終端）。"""

    flow_id: FlowId
    kind: Literal["handed_off"] = "handed_off"


# 状態の OR 型。fold(events) の戻り値。
BusinessFlowState = Union[
    ProposedFlow, ReviewingFlow, NeedsRevisionFlow, ApprovedFlow, HandedOffFlow
]
