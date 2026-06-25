"""Result 型 — DMMF。ドメインエラーは例外でなく Result で返す。sync #5。

#7 リファクタ時に shared/ へ移す候補（②救済 等と共通化）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar, Union

T = TypeVar("T")
E = TypeVar("E")


@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T


@dataclass(frozen=True)
class Err(Generic[E]):
    error: E


Result = Union[Ok[T], Err[E]]
