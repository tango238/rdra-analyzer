"""画面遷移の階層グラフ生成 — Projection（確度 derived・LLM 不要）。

入力:
- screen_specs: 画面（route_path / page_title / parent_page / child_pages /
  action_buttons[].target / shared_nav_items[].target）
- scenarios: loop-e2e 由来の操作シナリオ（steps の navigate/click から実走遷移を観測）

出力: Mermaid `flowchart TD`（上から下への階層）。
- entry: /login → /dashboard
- nav backbone: /dashboard → 各トップセクション（サイドバー由来・点線）
- drill-down: parent_page ＋ 前方向のリンク/ボタン（実線・ラベル付き）
- loop-e2e 実走エッジは太線で強調（linkStyle）

system_boundary と同じく、コード（画面）＋実績（シナリオ）から決定的に導出する派生図。
"""

import re


def _get(obj, key, default=None):
    """dict / dataclass どちらでも属性を引く。"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _norm_route(p):
    """URL / セレクタ片からルートパスを正規化して取り出す。"""
    if not p:
        return None
    p = str(p).strip()
    p = re.sub(r"^https?://[^/]+", "", p)  # origin 除去
    p = p.split("?")[0].split("#")[0]
    if not p.startswith("/"):
        return None
    if len(p) > 1:
        p = p.rstrip("/")
    return p or None


def _route_from_step(action, ui_element):
    """シナリオ step の action / ui_element から遷移先ルートを推定する。"""
    for text in (ui_element or "", action or ""):
        m = re.search(r"""href=['"]?([^'"\]\s>]+)""", text)
        if m:
            r = _norm_route(m.group(1))
            if r:
                return r
    for text in (ui_element or "", action or ""):
        m = re.search(r"""(https?://[^\s'"]+|/[\w:.\-/]*)""", text)
        if m:
            r = _norm_route(m.group(1))
            if r:
                return r
    return None


def _seg(route):
    return [s for s in route.strip("/").split("/") if s != ""]


def _is_placeholder(seg):
    return seg.startswith(":") or (seg.startswith("{") and seg.endswith("}"))


def _match_page(route, page_routes):
    """具体ルート（/reservations/rsv_2）をテンプレ画面（/reservations/:id）へ対応付ける。

    完全一致を優先し、無ければセグメント数一致 ＋ プレースホルダ・ワイルドカードで照合。
    """
    if route in page_routes:
        return route
    rseg = _seg(route)
    for pr in page_routes:
        pseg = _seg(pr)
        if len(pseg) != len(rseg):
            continue
        if all(_is_placeholder(p) or p == r for p, r in zip(pseg, rseg)):
            return pr
    return None


def _is_forward(src, tgt):
    """src → tgt が「掘り下げ（前方向）」か。tgt が src の祖先（戻りリンク）なら False。"""
    if tgt == src:
        return False
    sseg, tseg = _seg(src), _seg(tgt)
    # tgt が src の接頭辞（祖先）= 戻り
    if len(tseg) < len(sseg) and sseg[: len(tseg)] == tseg:
        return False
    return True


class ScreenFlowGenerator:
    """画面遷移の階層グラフ（Mermaid flowchart TD）を生成する。"""

    def generate_mermaid(self, screen_specs, scenarios) -> str:
        # ---- 画面（ノード）----
        pages = {}  # route -> title
        order = []
        nav_source = None
        for s in screen_specs or []:
            rp = _norm_route(_get(s, "route_path"))
            if not rp:
                continue
            if rp not in pages:
                order.append(rp)
            pages[rp] = _get(s, "page_title") or rp
            if nav_source is None and _get(s, "shared_nav_items"):
                nav_source = s

        if not pages:
            return 'flowchart TD\n  none["画面データがありません"]'

        page_routes = list(pages.keys())

        # ---- 実走エッジ（loop-e2e シナリオ）----
        observed = set()
        for sc in scenarios or []:
            seq = []
            for st in _get(sc, "steps", []) or []:
                act = _get(st, "action", "") or ""
                ui = _get(st, "ui_element", "") or ""
                if act.startswith("navigate") or act.startswith("click"):
                    r = _route_from_step(act, ui)
                    pr = _match_page(r, page_routes) if r else None
                    if pr:
                        seq.append(pr)
            for a, b in zip(seq, seq[1:]):
                if a != b:
                    observed.add((a, b))

        # ---- エッジ収集: (src, tgt) -> {"label", "kind"} ----
        edges = {}

        def add_edge(src, tgt, label, kind):
            if src not in pages or tgt not in pages or src == tgt:
                return
            cur = edges.get((src, tgt))
            if cur is None:
                edges[(src, tgt)] = {"label": label or "", "kind": kind}
            else:
                if label and not cur["label"]:
                    cur["label"] = label
                # nav < drill < entry の優先で kind を昇格
                rank = {"nav": 0, "drill": 1, "entry": 2}
                if rank.get(kind, 0) > rank.get(cur["kind"], 0):
                    cur["kind"] = kind

        # entry: /login -> /dashboard
        if "/login" in pages and "/dashboard" in pages:
            add_edge("/login", "/dashboard", "ログイン", "entry")

        # nav backbone: /dashboard -> 各トップセクション（サイドバー）
        nav_sections = []
        if nav_source is not None and "/dashboard" in pages:
            for n in _get(nav_source, "shared_nav_items", []) or []:
                t = _norm_route(_get(n, "target"))
                if not t or t in ("/dashboard", "/logout"):
                    continue
                tp = _match_page(t, page_routes)
                if tp and tp != "/dashboard":
                    add_edge("/dashboard", tp, "", "nav")
                    nav_sections.append(tp)

        # drill-down: parent_page ＋ 前方向の action_buttons / child_pages
        for s in screen_specs or []:
            rp = _norm_route(_get(s, "route_path"))
            if not rp or rp not in pages:
                continue
            parent = _norm_route(_get(s, "parent_page"))
            if parent:
                pp = _match_page(parent, page_routes)
                if pp and _is_forward(pp, rp):
                    add_edge(pp, rp, "", "drill")
            for b in _get(s, "action_buttons", []) or []:
                t = _norm_route(_get(b, "target"))
                if not t:
                    continue
                tp = _match_page(t, page_routes)
                if tp and _is_forward(rp, tp):
                    add_edge(rp, tp, (_get(b, "label") or "").strip(), "drill")
            for c in _get(s, "child_pages", []) or []:
                t = _norm_route(c)
                if not t:
                    continue
                tp = _match_page(t, page_routes)
                if tp and _is_forward(rp, tp):
                    add_edge(rp, tp, "", "drill")

        # 実走で観測したが静的に拾えていないエッジも追加
        for (a, b) in observed:
            add_edge(a, b, "", "drill")

        # ---- Mermaid 出力 ----
        def nid(route):
            slug = re.sub(r"[^0-9a-zA-Z]+", "_", route.strip("/")) or "root"
            return "s_" + slug

        def esc(text):
            # Mermaid ラベルで誤解されうる文字を無害化（波括弧はノード形状記法と衝突しうる）。
            return (
                str(text)
                .replace('"', "'")
                .replace("\n", " ")
                .replace("{", "").replace("}", "")
                .replace("[", "(").replace("]", ")")
                .replace("|", "/")
            )

        lines = ["flowchart TD"]
        for rp in order:
            lines.append(f'  {nid(rp)}["{esc(pages[rp])}<br/>{esc(rp)}"]')

        observed_link_indices = []
        idx = 0
        for (src, tgt), meta in edges.items():
            is_obs = (src, tgt) in observed
            label = meta["label"]
            if is_obs:
                label = (label + " ✓実走").strip() if label else "✓実走"
            arrow = "-.->" if meta["kind"] == "nav" and not is_obs else "-->"
            if label:
                lines.append(f'  {nid(src)} {arrow}|"{esc(label)}"| {nid(tgt)}')
            else:
                lines.append(f"  {nid(src)} {arrow} {nid(tgt)}")
            if is_obs:
                observed_link_indices.append(idx)
            idx += 1

        # 実走エッジを太線・緑で強調
        for i in observed_link_indices:
            lines.append(f"  linkStyle {i} stroke:#2E7D32,stroke-width:3px")

        # トップセクションを強調クラス
        if nav_sections:
            lines.append("  classDef section fill:#eef1ff,stroke:#4361ee,stroke-width:2px")
            ids = ",".join(nid(r) for r in dict.fromkeys(nav_sections))
            lines.append(f"  class {ids} section")
        if "/login" in pages:
            lines.append("  classDef entry fill:#fff3e0,stroke:#FF9800,stroke-width:2px")
            lines.append(f"  class {nid('/login')} entry")

        return "\n".join(lines)
