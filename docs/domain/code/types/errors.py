"""ドメインエラー — OR 型。例外でなく Result<_, BusinessFlowError> で返す。

由来: workflows.md（エラーカタログ）。ドメインエラー（UI 表示）と
技術例外（LoopE2eUnavailable）を仕分ける。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

from .value_objects import Status, UsecaseId


# --- ProposeError ---
@dataclass(frozen=True)
class NoConfirmedUsecases:
    kind: Literal["NoConfirmedUsecases"] = "NoConfirmedUsecases"


@dataclass(frozen=True)
class UnknownUsecase:
    uc_id: UsecaseId
    kind: Literal["UnknownUsecase"] = "UnknownUsecase"


@dataclass(frozen=True)
class UsecaseNotConfirmed:
    uc_id: UsecaseId
    kind: Literal["UsecaseNotConfirmed"] = "UsecaseNotConfirmed"


ProposeError = Union[NoConfirmedUsecases, UnknownUsecase, UsecaseNotConfirmed]


# --- TransitionError ---
@dataclass(frozen=True)
class IllegalTransition:
    from_status: Status
    command: str
    kind: Literal["IllegalTransition"] = "IllegalTransition"


TransitionError = IllegalTransition


# --- AuthError ---
@dataclass(frozen=True)
class NotPdM:
    actor: str
    kind: Literal["NotPdM"] = "NotPdM"


AuthError = NotPdM


# --- HandOffError ---
@dataclass(frozen=True)
class NotApproved:
    status: Status
    kind: Literal["NotApproved"] = "NotApproved"


@dataclass(frozen=True)
class LoopE2eUnavailable:
    """技術例外寄り（リトライ/ログ対象）。"""

    kind: Literal["LoopE2eUnavailable"] = "LoopE2eUnavailable"


HandOffError = Union[NotApproved, LoopE2eUnavailable]


# --- ワークフロー全体のエラー OR 型 ---
BusinessFlowError = Union[ProposeError, TransitionError, AuthError, HandOffError]
