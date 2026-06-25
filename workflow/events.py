"""業務フローのドメインイベント（Event Sourcing のストリーム要素）。sync #5。

由来: domain-events.md（BC ③・Enrichment・occurredOn 必須）。
追記専用 JSONL に保存し、fold で状態を復元する。to_dict/from_dict は store 用。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

FlowId = str
UsecaseId = str
Timestamp = str  # ISO8601


@dataclass(frozen=True)
class BusinessFlowProposed:
    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    occurred_on: Timestamp
    kind: Literal["BusinessFlowProposed"] = "BusinessFlowProposed"


@dataclass(frozen=True)
class BusinessFlowReviewed:
    flow_id: FlowId
    by: Literal["PdM"]
    occurred_on: Timestamp
    kind: Literal["BusinessFlowReviewed"] = "BusinessFlowReviewed"


@dataclass(frozen=True)
class BusinessFlowFeedbackGiven:
    flow_id: FlowId
    by: Literal["PdM"]
    feedback: str
    occurred_on: Timestamp
    kind: Literal["BusinessFlowFeedbackGiven"] = "BusinessFlowFeedbackGiven"


@dataclass(frozen=True)
class BusinessFlowReProposed:
    flow_id: FlowId
    uc_ids: tuple[UsecaseId, ...]
    occurred_on: Timestamp
    kind: Literal["BusinessFlowReProposed"] = "BusinessFlowReProposed"


@dataclass(frozen=True)
class BusinessFlowEdited:
    flow_id: FlowId
    by: Literal["PdM"]
    edits: str
    occurred_on: Timestamp
    kind: Literal["BusinessFlowEdited"] = "BusinessFlowEdited"


@dataclass(frozen=True)
class BusinessFlowApproved:
    flow_id: FlowId
    approver: Literal["PdM"]
    occurred_on: Timestamp
    kind: Literal["BusinessFlowApproved"] = "BusinessFlowApproved"


@dataclass(frozen=True)
class ApprovedFlowHandedOff:
    flow_id: FlowId
    occurred_on: Timestamp
    kind: Literal["ApprovedFlowHandedOff"] = "ApprovedFlowHandedOff"


BusinessFlowEvent = Union[
    BusinessFlowProposed,
    BusinessFlowReviewed,
    BusinessFlowFeedbackGiven,
    BusinessFlowReProposed,
    BusinessFlowEdited,
    BusinessFlowApproved,
    ApprovedFlowHandedOff,
]

_EVENT_TYPES = {
    cls.__name__: cls
    for cls in (
        BusinessFlowProposed,
        BusinessFlowReviewed,
        BusinessFlowFeedbackGiven,
        BusinessFlowReProposed,
        BusinessFlowEdited,
        BusinessFlowApproved,
        ApprovedFlowHandedOff,
    )
}


def to_dict(ev: BusinessFlowEvent) -> dict:
    d = {**ev.__dict__}
    if "uc_ids" in d:
        d["uc_ids"] = list(d["uc_ids"])
    return d


def from_dict(d: dict) -> BusinessFlowEvent:
    cls = _EVENT_TYPES[d["kind"]]
    kwargs = {k: v for k, v in d.items() if k != "kind"}
    if "uc_ids" in kwargs:
        kwargs["uc_ids"] = tuple(kwargs["uc_ids"])
    return cls(**kwargs)
