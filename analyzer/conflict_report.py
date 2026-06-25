"""矛盾検出 ＋ 要調査フラグ — sync 差異 #4。

「静的で確定 ＋ loop-e2e 実績と矛盾」したとき、**コードを真**とし（UC は上書きしない）、
矛盾を別レポートに「要調査」として記録して PdM に提示する。確定モデルは汚さない
（棄却ログ #1 と対称の独立出力）。

矛盾の判定は reconcile 側の決定的ルールで行い（`detect_conflicts`）、本モジュールは
その結果（`Conflict`）の保持・シリアライズに専念する。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Conflict:
    """実績と UC 宣言の食い違い。コードを真とし、要調査として記録する。"""

    usecase_id: str
    kind: str          # "actor_mismatch" | "controller_mismatch"
    detail: str        # 人間向けの説明
    code_value: str    # コード（UC 宣言）側＝真とする値
    actual_value: str  # loop-e2e 実績側の値


def conflict_to_dict(c: Conflict) -> dict:
    return {
        "usecase_id": c.usecase_id,
        "kind": c.kind,
        "detail": c.detail,
        "code_value": c.code_value,
        "actual_value": c.actual_value,
    }


def load_conflicts(data: dict) -> list[Conflict]:
    """矛盾レポート JSON から復元する。旧スキーマ（欠落キー）に強い。"""
    out: list[Conflict] = []
    for c in data.get("conflicts", []):
        out.append(
            Conflict(
                usecase_id=c["usecase_id"],
                kind=c.get("kind", ""),
                detail=c.get("detail", ""),
                code_value=c.get("code_value", ""),
                actual_value=c.get("actual_value", ""),
            )
        )
    return out
