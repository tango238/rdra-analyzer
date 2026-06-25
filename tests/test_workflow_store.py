"""業務フローの append-only イベントストア（ES 永続化）のテスト — sync #5。"""

from pathlib import Path

import pytest

from workflow.events import (
    BusinessFlowApproved,
    BusinessFlowProposed,
    BusinessFlowReviewed,
)
from workflow.state import ApprovedFlow, fold
from workflow.store import append, flow_path, load


def test_load_missing_returns_empty(tmp_path: Path) -> None:
    assert load(flow_path(tmp_path, "BF-X")) == []


def test_append_then_load_roundtrip(tmp_path: Path) -> None:
    p = flow_path(tmp_path, "BF-1")
    ev = BusinessFlowProposed("BF-1", ("UC-001", "UC-002"), "t0")
    append(p, ev)
    loaded = load(p)
    assert loaded == [ev]
    assert loaded[0].uc_ids == ("UC-001", "UC-002")  # tuple 復元


def test_append_is_additive(tmp_path: Path) -> None:
    p = flow_path(tmp_path, "BF-1")
    append(p, BusinessFlowProposed("BF-1", ("UC-001",), "t0"))
    append(p, BusinessFlowReviewed("BF-1", "PdM", "t1"))
    append(p, BusinessFlowApproved("BF-1", "PdM", "t2"))
    loaded = load(p)
    assert len(loaded) == 3
    state = fold(loaded)
    assert isinstance(state, ApprovedFlow)


def test_load_reconstructs_via_fold(tmp_path: Path) -> None:
    p = flow_path(tmp_path, "BF-7")
    append(p, BusinessFlowProposed("BF-7", ("UC-001",), "t0"))
    assert fold(load(p)).flow_id == "BF-7"


@pytest.mark.parametrize(
    "bad",
    ["../evil", "../../etc/passwd", "a/b", "..", "with/slash", "back\\slash", "dot.ted", ""],
)
def test_flow_path_rejects_unsafe_ids(tmp_path: Path, bad: str) -> None:
    # flow_id は CLI 自由入力。パス区切りや .. を ID に混ぜて business_flows 外へ
    # 書き込めてはならない（Codex P2 パストラバーサル）。
    with pytest.raises(ValueError):
        flow_path(tmp_path, bad)


def test_flow_path_accepts_normal_ids(tmp_path: Path) -> None:
    p = flow_path(tmp_path, "BF-1")
    assert p.name == "BF-1.jsonl"
    assert p.parent.name == "business_flows"
