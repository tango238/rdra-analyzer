"""Precision 棄却 ＋ 棄却ログ — sync 差異 #1。

Core の不変条件「抽出要素 → コード証拠の対応が常に存在する。根拠なき UC は確定モデルに出さない」を
実装に落とす。ただし **棄却＝破棄ではない**：理由と欠落証拠を棄却ログへ残し、検証フロー
（loop-e2e 実績による救済など）の入力にする。

棄却の判定はコード証拠アンカー（ルート / コントローラ / エンティティ / 画面）が
**一つも無い** UC を「証拠の連鎖が切れている」とみなす決定的ルール。LLM は使わない。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from extraction.usecase_extractor import UseCase

# UC をコードへ接地する証拠アンカー。いずれか1つでもあれば確定モデルに残す。
_EVIDENCE_FIELDS: tuple[str, ...] = (
    "related_routes",
    "related_controllers",
    "related_entities",
    "related_pages",
)

_REJECT_REASON = "コード証拠（ルート/コントローラ/エンティティ/画面）に紐づかない"


@dataclass
class RejectedUsecase:
    """確定モデルから棄却された UC の記録。破棄せず検証フローへ回す。"""

    id: str
    name: str
    reason: str
    missing_evidence: list[str] = field(default_factory=list)


def _anchors(uc: UseCase) -> dict[str, list[str]]:
    return {f: list(getattr(uc, f) or []) for f in _EVIDENCE_FIELDS}


def has_code_evidence(uc: UseCase) -> bool:
    """UC がコード証拠アンカーを1つでも持つか。"""
    return any(_anchors(uc).values())


def missing_evidence(uc: UseCase) -> list[str]:
    """空になっている証拠アンカーのフィールド名一覧（欠落証拠）。"""
    return [name for name, values in _anchors(uc).items() if not values]


def partition_usecases(
    usecases: list[UseCase],
) -> tuple[list[UseCase], list[RejectedUsecase]]:
    """確定（証拠あり）と棄却（証拠なし）に分割する。入力は破壊しない。"""
    confirmed: list[UseCase] = []
    rejected: list[RejectedUsecase] = []
    for uc in usecases:
        if has_code_evidence(uc):
            confirmed.append(uc)
        else:
            rejected.append(
                RejectedUsecase(
                    id=uc.id,
                    name=uc.name,
                    reason=_REJECT_REASON,
                    missing_evidence=missing_evidence(uc),
                )
            )
    return confirmed, rejected


def rejected_to_dict(r: RejectedUsecase) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "reason": r.reason,
        "missing_evidence": r.missing_evidence,
    }


def load_rejected(data: dict) -> list[RejectedUsecase]:
    """棄却ログ JSON から復元する。旧スキーマ（欠落キー）に強い。"""
    out: list[RejectedUsecase] = []
    for r in data.get("rejected", []):
        out.append(
            RejectedUsecase(
                id=r["id"],
                name=r.get("name", ""),
                reason=r.get("reason", ""),
                missing_evidence=list(r.get("missing_evidence", [])),
            )
        )
    return out
