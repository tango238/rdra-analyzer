"""依存（ポート）— 関数型シグネチャ。DMMF: 依存は関数引数で渡す（DI コンテナ無し）。

由来: workflows.md（依存ポート一覧）。副作用は両端に寄せる。
"""

from __future__ import annotations

from typing import Callable, Sequence

from util.result import Result

from .events import ApprovedFlowHandedOff, BusinessFlowEvent
from .errors import HandOffError
from .states import ApprovedFlow
from .value_objects import FlowId, Timestamp, UsecaseId

# ① Shared Kernel(analysis_result.json) から確定UCの id を読む（read-only）。
# 実装は full Usecase を返すが、ワークフローは id の集合だけ必要。② 救済と共通化候補。
LoadConfirmedUsecases = Callable[[], Sequence[UsecaseId]]

# ES ストア（append-only JSONL）。fold の前段で全件 load、各コマンド成功で 1 件 append。
LoadFlowEvents = Callable[[FlowId], Sequence[BusinessFlowEvent]]
AppendFlowEvent = Callable[[FlowId, BusinessFlowEvent], None]

# loop-e2e への引き渡し（PL outbound・send-message）。失敗は Result に現れる。
HandOffToLoopE2e = Callable[[ApprovedFlow], "Result[None, HandOffError]"]

# 時刻（occurredOn 用）。純粋性を保つため依存として注入。
Now = Callable[[], Timestamp]
