"""Value Object — Simple 型（ブランド）＋ Status の値域。

由来: aggregates.md（VO）/ workflows.md（Status）/ glossary.md（用語）。
"""

from __future__ import annotations

from typing import Literal, NewType

# ブランド型（Simple 型）: 生の str と取り違えないための識別子
FlowId = NewType("FlowId", str)
UsecaseId = NewType("UsecaseId", str)
Timestamp = NewType("Timestamp", str)  # ISO8601

# アクター（OR 値）。承認・FB・編集は PdM のみ（不変条件）
Actor = Literal["PdM", "System"]

# 業務フローの状態値域。各状態は states.py の専用型に対応（不正状態を表現不能に）
Status = Literal["proposed", "reviewing", "needs_revision", "approved", "handed_off"]
