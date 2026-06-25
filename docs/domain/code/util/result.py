"""Result 型 — DMMF。ドメインエラーは例外でなく Result で返す。

Phase 10 (types) の基盤ユーティリティ。実装言語は本プロジェクトに合わせ Python。
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
