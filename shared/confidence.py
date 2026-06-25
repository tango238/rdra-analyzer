"""確度ラベル (Confidence) — 抽出物の根拠の強さを表す三値。

sync 差異 #2。ドメインモデルの「確定層／派生層」区別をコードに落とす土台。

- ``confirmed``: コード証拠と 1:1 で裏付く確定層（ユースケース・エンティティ操作）。
- ``derived``: 確定層から決定的に導出した派生層（情報モデル・状態遷移・BP・CRUD ギャップ・システム境界）。
- ``inferred``: LLM 推論や reconcile 合成など、コード証拠の裏付けが弱いもの。

棄却判定（#1）・矛盾検出（#4）はこのラベルを入力に使う。
"""

from typing import Literal

Confidence = Literal["confirmed", "derived", "inferred"]

CONFIRMED: Confidence = "confirmed"
DERIVED: Confidence = "derived"
INFERRED: Confidence = "inferred"

# 確度の順序（高いほどコード証拠が強い）。棄却の閾値判定に使う。
_ORDER: dict[str, int] = {"confirmed": 2, "derived": 1, "inferred": 0}


def rank(value: Confidence) -> int:
    """確度を数値順序へ。``confirmed`` > ``derived`` > ``inferred``。"""
    return _ORDER[value]


def coerce(value: str | None, default: Confidence = CONFIRMED) -> Confidence:
    """永続化された文字列を ``Confidence`` へ安全に正規化する。

    未知の値・``None``（旧スキーマの checkpoint 等）は ``default`` にフォールバックし、
    スキーマドリフトに強くする。
    """
    if value in _ORDER:
        return value  # type: ignore[return-value]
    return default
