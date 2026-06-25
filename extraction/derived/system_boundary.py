"""システム境界図生成モジュール — sync 差異 #3。

RDRA のシステム境界を Mermaid flowchart で描く。境界の外にアクター、境界の中に
**接点（画面）** と **起点（API エンドポイント）** を置き、UC ごとに
アクター → 接点 → 起点 のつながりを引く。

enrich の照合結果（`related_pages` / `related_views` / `related_routes`）から
**決定的に**生成する（LLM 不要）。よって出力の確度は派生層（derived）相当。
新規生成ではなく既存照合の「意味づけ」（event-storming の赤付箋）。
"""

from __future__ import annotations

import hashlib
import re

from extraction.usecase_extractor import UseCase


def _safe_id(prefix: str, text: str) -> str:
    """Mermaid ノード ID を決定的に生成する。

    ASCII 英数字は可読性のため slug として残すが、非 ASCII（日本語アクター・
    画面名が通常ケース）は ASCII へ畳むと全消失し別ノードが同一 ID に潰れる。
    そこで原文の短いハッシュを必ず付与し、異なるテキストは必ず異なる ID にする。
    純粋関数なのでノード定義・エッジ・class 参照すべてで一貫する。
    """
    slug = re.sub(r"[^0-9A-Za-z]+", "_", text).strip("_")
    digest = hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{slug}_{digest}" if slug else f"{prefix}_{digest}"


def _esc(text: str) -> str:
    """ノードラベル中の二重引用符を安全化する。"""
    return text.replace('"', "'")


class SystemBoundaryGenerator:
    """確定 UC 群からシステム境界図（接点 × 起点）を生成する。決定的・LLM 不要。"""

    def generate_mermaid(self, usecases: list[UseCase]) -> str:
        lines = ["---", "title: システム境界図", "---", "flowchart LR"]

        actors = sorted({uc.actor for uc in usecases if uc.actor})
        screens = sorted(
            {s for uc in usecases for s in (list(uc.related_pages) + list(uc.related_views)) if s}
        )
        endpoints = sorted({r for uc in usecases for r in uc.related_routes if r})

        # アクター（境界の外）
        lines.append("")
        lines.append("    %% アクター（システム境界の外）")
        for a in actors:
            lines.append(f'    {_safe_id("actor", a)}(["👤 {_esc(a)}"])')

        # システム境界（接点＝画面 / 起点＝エンドポイント）
        lines.append("")
        lines.append('    subgraph SYS["システム境界"]')
        lines.append("        %% 接点（画面）")
        for s in screens:
            lines.append(f'        {_safe_id("screen", s)}["🖥 {_esc(s)}"]')
        lines.append("        %% 起点（API エンドポイント）")
        for e in endpoints:
            lines.append(f'        {_safe_id("ep", e)}[/"🔌 {_esc(e)}"/]')
        lines.append("    end")

        # アクター → 接点 → 起点（UC 内の対応から）。重複辺は除く。
        lines.append("")
        lines.append("    %% アクター → 接点 → 起点")
        seen: set[tuple[str, str]] = set()

        def _edge(src: str, dst: str) -> None:
            if (src, dst) not in seen:
                seen.add((src, dst))
                lines.append(f"    {src} --> {dst}")

        for uc in usecases:
            if not uc.actor:
                continue
            a_id = _safe_id("actor", uc.actor)
            uc_screens = [s for s in (list(uc.related_pages) + list(uc.related_views)) if s]
            uc_endpoints = [e for e in uc.related_routes if e]
            if uc_screens:
                for s in uc_screens:
                    s_id = _safe_id("screen", s)
                    _edge(a_id, s_id)
                    for e in uc_endpoints:
                        _edge(s_id, _safe_id("ep", e))
            else:
                # 接点が無い場合はアクターから起点へ直結
                for e in uc_endpoints:
                    _edge(a_id, _safe_id("ep", e))

        # スタイル
        lines.append("")
        lines.append("    classDef actor fill:#e8f4fd,stroke:#2196F3,stroke-width:2px")
        lines.append("    classDef screen fill:#fff3e0,stroke:#FF9800")
        lines.append("    classDef endpoint fill:#e8f5e9,stroke:#2E7D32")
        for a in actors:
            lines.append(f'    class {_safe_id("actor", a)} actor')
        for s in screens:
            lines.append(f'    class {_safe_id("screen", s)} screen')
        for e in endpoints:
            lines.append(f'    class {_safe_id("ep", e)} endpoint')

        return "\n".join(lines)
