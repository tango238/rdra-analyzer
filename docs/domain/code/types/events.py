"""業務フローのドメインイベント — OR 型（Event Sourcing のストリーム要素）。

由来: domain-events.md（BC ③・Enrichment・全イベント occurredOn 必須）。
状態は fold([events]) で復元する（ES）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from .value_objects import FlowId, Timestamp, UsecaseId


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
