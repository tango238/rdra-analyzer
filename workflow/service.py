"""業務フロー承認ループのオーケストレーション（副作用の境界）。sync #5。

由来: workflows.md（副作用は両端・依存は関数引数）。

純粋なコマンド（commands.py）と純粋な fold（state.py）を、I/O（イベントストア・
確定UC読込・loop-e2e 引き渡し成果物）で挟む。DMMF「I/O at the edges」。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from . import commands
from .errors import IllegalTransition
from .result import Err, Ok, Result
from .state import BusinessFlowState, fold, status_of
from .store import append, flow_path, load


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_confirmed_uc_ids(analysis: dict) -> set[str]:
    """① Shared Kernel(analysis_result.json) から確定(confirmed)UC の id 集合を得る。

    確度ラベル（sync #2）が `confirmed` のもののみ。旧スキーマ（confidence 欠落）は
    既定 confirmed として扱う。
    """
    return {
        u["id"]
        for u in analysis.get("usecases", [])
        if u.get("confidence", "confirmed") == "confirmed" and u.get("id")
    }


def current_state(base_dir: Path, flow_id: str) -> Optional[BusinessFlowState]:
    return fold(load(flow_path(base_dir, flow_id)))


def _append_on_ok(base_dir: str, flow_id: str, result: Result) -> Result:
    if isinstance(result, Ok):
        append(flow_path(base_dir, flow_id), result.value)
    return result


def propose(
    base_dir: Path,
    flow_id: str,
    uc_ids: Iterable[str],
    confirmed_uc_ids: set[str],
    now: Optional[str] = None,
) -> Result:
    if current_state(base_dir, flow_id) is not None:
        return Err(IllegalTransition(status_of(current_state(base_dir, flow_id)), "propose"))
    r = commands.propose_flow(flow_id, uc_ids, confirmed_uc_ids, now or _now())
    return _append_on_ok(base_dir, flow_id, r)


def review(base_dir: Path, flow_id: str, actor: str, now: Optional[str] = None) -> Result:
    r = commands.review_flow(current_state(base_dir, flow_id), actor, now or _now())
    return _append_on_ok(base_dir, flow_id, r)


def feedback(
    base_dir: Path, flow_id: str, actor: str, text: str, now: Optional[str] = None
) -> Result:
    r = commands.give_feedback(current_state(base_dir, flow_id), actor, text, now or _now())
    return _append_on_ok(base_dir, flow_id, r)


def re_propose(
    base_dir: Path, flow_id: str, confirmed_uc_ids: set[str], now: Optional[str] = None
) -> Result:
    r = commands.re_propose_flow(current_state(base_dir, flow_id), confirmed_uc_ids, now or _now())
    return _append_on_ok(base_dir, flow_id, r)


def edit(
    base_dir: Path, flow_id: str, actor: str, edits: str, now: Optional[str] = None
) -> Result:
    r = commands.edit_flow(current_state(base_dir, flow_id), actor, edits, now or _now())
    return _append_on_ok(base_dir, flow_id, r)


def approve(base_dir: Path, flow_id: str, actor: str, now: Optional[str] = None) -> Result:
    r = commands.approve_flow(current_state(base_dir, flow_id), actor, now or _now())
    return _append_on_ok(base_dir, flow_id, r)


def handoff(base_dir: Path, flow_id: str, now: Optional[str] = None) -> Result:
    """承認済みフローを loop-e2e へ引き渡す（Published Language 成果物を出力）。"""
    state = current_state(base_dir, flow_id)
    r = commands.hand_off(state, now or _now())
    if isinstance(r, Ok):
        # loop-e2e へ渡す PL 成果物を書き出す（実 I/O はここ＝境界）
        artifact = flow_path(base_dir, flow_id).with_suffix(".handoff.json")
        artifact.write_text(
            json.dumps(
                {
                    "flow_id": state.flow_id,
                    "uc_ids": list(state.uc_ids),
                    "approver": state.approver,
                    "handed_off_on": r.value.occurred_on,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        append(flow_path(base_dir, flow_id), r.value)
    return r
