"""業務フローの append-only イベントストア（Event Sourcing 永続化）。sync #5。

由来: workflows.md（依存 LoadFlowEvents / AppendFlowEvent・副作用は両端）。

1 業務フロー = 1 JSONL ファイル（1 行 1 イベント）。**追記のみ**で上書きしない＝
イベント履歴が真実。状態は load → fold で復元する。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .events import BusinessFlowEvent, from_dict, to_dict

# flow_id は `rdra flow ...` の自由入力引数。パス区切りや `..` を混ぜると
# business_flows 配下の外（出力ディレクトリの外）へ書き込めてしまうため、
# ファイル名に安全な文字（英数字・ハイフン・アンダースコア）のみ許可する。
_SAFE_FLOW_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def flow_path(base_dir: Path, flow_id: str) -> Path:
    """業務フロー ID から JSONL ファイルパスを得る。

    flow_id を検証し、パストラバーサル（`../`, 絶対パス, `.` 等）を拒否する。
    """
    if not _SAFE_FLOW_ID.match(flow_id):
        raise ValueError(
            f"invalid flow_id: {flow_id!r} "
            "(英数字・'-'・'_' のみ許可。パス区切りや '..' は不可)"
        )
    return Path(base_dir) / "business_flows" / f"{flow_id}.jsonl"


def load(path: Path) -> list[BusinessFlowEvent]:
    """イベント列を全件読み込む。ファイルが無ければ空。"""
    if not path.exists():
        return []
    out: list[BusinessFlowEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(from_dict(json.loads(line)))
    return out


def append(path: Path, ev: BusinessFlowEvent) -> None:
    """イベントを 1 件追記する（上書きしない）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(to_dict(ev), ensure_ascii=False) + "\n")
