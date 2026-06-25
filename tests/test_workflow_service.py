"""業務フロー承認ループのオーケストレーション（load→fold→command→append）— sync #5。

I/O を含むサービス層。base_dir=tmp_path で永続化を検証する。
"""

import json
from pathlib import Path

from workflow import service
from workflow.errors import IllegalTransition, NotPdM
from workflow.result import Err, Ok
from workflow.store import flow_path, load


def test_full_approval_loop_persists_and_hands_off(tmp_path: Path) -> None:
    confirmed = {"UC-001", "UC-002"}
    assert isinstance(
        service.propose(tmp_path, "BF-1", ("UC-001",), confirmed, now="t0"), Ok
    )
    assert isinstance(service.review(tmp_path, "BF-1", actor="PdM", now="t1"), Ok)
    assert isinstance(service.approve(tmp_path, "BF-1", actor="PdM", now="t2"), Ok)
    r = service.handoff(tmp_path, "BF-1", now="t3")
    assert isinstance(r, Ok)

    # 4 イベントが追記され、状態は handed_off
    events = load(flow_path(tmp_path, "BF-1"))
    assert len(events) == 4
    assert service.current_state(tmp_path, "BF-1").kind == "handed_off"

    # loop-e2e への引き渡し成果物（PL）が出力される
    artifact = tmp_path / "business_flows" / "BF-1.handoff.json"
    assert artifact.exists()
    payload = json.loads(artifact.read_text())
    assert payload["flow_id"] == "BF-1"
    assert payload["uc_ids"] == ["UC-001"]


def test_approve_before_review_is_rejected_and_not_appended(tmp_path: Path) -> None:
    service.propose(tmp_path, "BF-2", ("UC-001",), {"UC-001"}, now="t0")
    r = service.approve(tmp_path, "BF-2", actor="PdM", now="t1")
    assert isinstance(r, Err) and isinstance(r.error, IllegalTransition)
    # guard 違反は永続化されない（1 件のまま）
    assert len(load(flow_path(tmp_path, "BF-2"))) == 1


def test_non_pdm_approve_rejected(tmp_path: Path) -> None:
    service.propose(tmp_path, "BF-3", ("UC-001",), {"UC-001"}, now="t0")
    service.review(tmp_path, "BF-3", actor="PdM", now="t1")
    r = service.approve(tmp_path, "BF-3", actor="System", now="t2")
    assert isinstance(r, Err) and isinstance(r.error, NotPdM)


def test_propose_twice_rejected(tmp_path: Path) -> None:
    assert isinstance(service.propose(tmp_path, "BF-4", ("UC-001",), {"UC-001"}, now="t0"), Ok)
    r = service.propose(tmp_path, "BF-4", ("UC-001",), {"UC-001"}, now="t1")
    assert isinstance(r, Err)


def test_load_confirmed_uc_ids_filters_by_confidence() -> None:
    analysis = {"usecases": [
        {"id": "UC-001", "confidence": "confirmed"},
        {"id": "UC-LE-001", "confidence": "inferred"},
        {"id": "UC-002"},  # legacy: default confirmed
    ]}
    assert service.load_confirmed_uc_ids(analysis) == {"UC-001", "UC-002"}
