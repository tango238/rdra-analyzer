"""ドメインエラー — OR 型。例外でなく Result<_, BusinessFlowError> で返す。sync #5。

由来: workflows.md（エラーカタログ）/ code/types/errors.py（Phase 10）。
ドメインエラー（UI 表示）と技術例外（LoopE2eUnavailable）を仕分ける。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class NoConfirmedUsecases:
    pass


@dataclass(frozen=True)
class UnknownUsecase:
    uc_id: str


@dataclass(frozen=True)
class UsecaseNotConfirmed:
    uc_id: str


@dataclass(frozen=True)
class IllegalTransition:
    from_status: str
    command: str


@dataclass(frozen=True)
class NotPdM:
    actor: str


@dataclass(frozen=True)
class NotApproved:
    status: str


@dataclass(frozen=True)
class LoopE2eUnavailable:
    """技術例外寄り（リトライ/ログ対象）。"""


ProposeError = Union[NoConfirmedUsecases, UnknownUsecase, UsecaseNotConfirmed]
HandOffError = Union[NotApproved, LoopE2eUnavailable]
BusinessFlowError = Union[
    ProposeError, IllegalTransition, NotPdM, HandOffError
]
