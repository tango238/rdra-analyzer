"""業務フロー承認ループ — ステップ（コマンド）の関数型シグネチャ。

由来: workflows.md（Workflow 1・各ステップ）。型シグネチャのみ（本体は sync で実装）。

DMMF: 各コマンドは (現状態, 入力, 依存) → Result<Event, Error>。状態は fold で前段復元。
不正状態を表現不能に: approve は ReviewingFlow のみ、handOff は ApprovedFlow のみを受ける。
"""

from __future__ import annotations

from typing import Callable, Sequence

from util.result import Result

from .errors import (
    AuthError,
    BusinessFlowError,
    HandOffError,
    ProposeError,
    TransitionError,
)
from .events import (
    ApprovedFlowHandedOff,
    BusinessFlowApproved,
    BusinessFlowEdited,
    BusinessFlowEvent,
    BusinessFlowFeedbackGiven,
    BusinessFlowProposed,
    BusinessFlowReProposed,
    BusinessFlowReviewed,
)
from .ports import LoadConfirmedUsecases, HandOffToLoopE2e, Now
from .states import (
    ApprovedFlow,
    BusinessFlowState,
    NeedsRevisionFlow,
    ProposedFlow,
    ReviewingFlow,
)
from .value_objects import Actor, UsecaseId

# ES の心臓: イベント列を畳み込んで現在状態を復元（純粋）。
Fold = Callable[[Sequence[BusinessFlowEvent]], BusinessFlowState]

# --- コマンド（ステップ）の関数型 ---

# proposeFlow: 確定UC群から想定。LoadConfirmedUsecases で uc_ids の実在/確定を検証。
ProposeFlow = Callable[
    [LoadConfirmedUsecases, Now, tuple[UsecaseId, ...]],
    "Result[BusinessFlowProposed, ProposeError]",
]

# reviewFlow: PdM レビュー着手。ProposedFlow のみ。
ReviewFlow = Callable[
    [ProposedFlow, Actor, Now],
    "Result[BusinessFlowReviewed, AuthError | TransitionError]",
]

# giveFeedback: PdM 差し戻し。ReviewingFlow のみ。
GiveFeedback = Callable[
    [ReviewingFlow, Actor, str, Now],
    "Result[BusinessFlowFeedbackGiven, AuthError]",
]

# reProposeFlow: System 再想定（自動）。NeedsRevisionFlow のみ。
ReProposeFlow = Callable[
    [NeedsRevisionFlow, LoadConfirmedUsecases, Now],
    "Result[BusinessFlowReProposed, ProposeError]",
]

# editFlow: PdM 手動微調整（Proposed/Reviewing/NeedsRevision で可）。
EditFlow = Callable[
    [BusinessFlowState, Actor, str, Now],
    "Result[BusinessFlowEdited, AuthError | TransitionError]",
]

# approveFlow: PdM 承認＝確定。ReviewingFlow のみ。guard: actor=PdM。
ApproveFlow = Callable[
    [ReviewingFlow, Actor, Now],
    "Result[BusinessFlowApproved, AuthError | TransitionError]",
]

# handOff: 承認済みを loop-e2e へ。ApprovedFlow のみ（型で未承認を排除）。
HandOff = Callable[
    [ApprovedFlow, HandOffToLoopE2e, Now],
    "Result[ApprovedFlowHandedOff, HandOffError]",
]
