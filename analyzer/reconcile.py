"""
loop-e2e 連携 — reconcile モジュール

loop-e2e の `rdra-export` が書き出す `loop-e2e-pending.json`（ルート照合で
当たらなかったシナリオ）を rdra-analyzer 側で取り込む。

各 pending エントリを checkpoint（routes / pages / controllers）でソースに当てて
事実確認し、既存ユースケースに紐付ける。該当が無ければ新規ユースケースを生成して
取り込む。出力は常に参照整合（dangling usecase_id 無し）を保つ。

正規化規則（normalize_route）は loop-e2e の spec と同一実装（METHODトークン除去・
ANYワイルドカード・origin/クエリ/フラグメント/末尾スラッシュ除去）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import Optional

from confidence import DERIVED, INFERRED, coerce
from .conflict_report import Conflict
from .rejection_log import RejectedUsecase
from .scenario_builder import OperationScenario, OperationStep
from .usecase_extractor import Usecase

_METHOD_RE = re.compile(
    r"^(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS|ANY)\s+", re.IGNORECASE
)


# --------------------------------------------------------------------------- #
# ルートキー・正規化（loop-e2e と同一実装）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RouteKey:
    """正規化済みルート (method, path)。method=ANY はワイルドカード。"""

    method: str
    path: str


def normalize_path(p: str) -> str:
    """origin・クエリ・フラグメント・末尾スラッシュを除去（root は維持）。"""
    p = (p or "").strip()
    p = re.sub(r"^https?://[^/]+", "", p)  # origin 除去
    p = p.split("?", 1)[0].split("#", 1)[0]  # クエリ/フラグメント除去
    p = p.strip()
    if not p:
        return "/"
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1:
        p = p.rstrip("/")
    return p or "/"


def normalize_route(s: str) -> RouteKey:
    """`"<METHOD> <path>"` 文字列を RouteKey に正規化。METHOD 省略時は ANY。"""
    t = (s or "").strip()
    m = _METHOD_RE.match(t)
    if m:
        method = m.group(1).upper()
        rest = t[m.end():]
    else:
        method = "ANY"
        rest = t
    return RouteKey(method, normalize_path(rest))


def method_matches(a: str, b: str) -> bool:
    return a == "ANY" or b == "ANY" or a == b


def route_key_equals(x: RouteKey, y: RouteKey) -> bool:
    return method_matches(x.method, y.method) and x.path == y.path


def _is_placeholder(seg: str) -> bool:
    return seg.startswith(":") or (seg.startswith("{") and seg.endswith("}"))


def path_matches_template(concrete: str, template: str) -> bool:
    """checkpoint ルート（`:param` / `{param}` を含む）に対する具体パスの照合。"""
    a = [s for s in concrete.strip("/").split("/") if s != ""]
    b = [s for s in template.strip("/").split("/") if s != ""]
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if _is_placeholder(y):
            continue
        if x != y:
            return False
    return True


def route_key_matches_template(key: RouteKey, template: RouteKey) -> bool:
    return method_matches(key.method, template.method) and path_matches_template(
        key.path, template.path
    )


def _path_prefix(a: str, b: str) -> bool:
    """一方が他方のパスプレフィックスか（セグメント単位）。"""
    sa = [s for s in a.strip("/").split("/") if s != ""]
    sb = [s for s in b.strip("/").split("/") if s != ""]
    n = min(len(sa), len(sb))
    if n == 0:
        return False
    return sa[:n] == sb[:n]


# --------------------------------------------------------------------------- #
# pending エントリ
# --------------------------------------------------------------------------- #
@dataclass
class PendingEntry:
    loop_e2e_id: str
    scenario_name: str = ""
    frontend_url: str = ""
    navigate_routes: list[str] = field(default_factory=list)
    api_endpoints: list[dict] = field(default_factory=list)  # {method, path, raw}
    steps: list[dict] = field(default_factory=list)
    reason: str = ""

    @staticmethod
    def from_dict(d: dict) -> "PendingEntry":
        return PendingEntry(
            loop_e2e_id=d.get("loop_e2e_id", ""),
            scenario_name=d.get("scenario_name", ""),
            frontend_url=d.get("frontend_url", ""),
            navigate_routes=list(d.get("navigate_routes", [])),
            api_endpoints=[_parse_api_endpoint(x) for x in d.get("api_endpoints", [])],
            steps=list(d.get("steps", [])),
            reason=d.get("reason", ""),
        )


def _parse_api_endpoint(item) -> dict:
    """`{method, path, raw}` 構造化。レガシー文字列は best-effort パース。"""
    if isinstance(item, dict):
        return {
            "method": (item.get("method") or None),
            "path": (item.get("path") or None),
            "raw": item.get("raw", ""),
        }
    s = str(item)
    t = s.strip()
    m = _METHOD_RE.match(t)
    method = m.group(1).upper() if m else None
    rest = t[m.end():] if m else t
    # best-effort: METHOD 後の最初のトークンが "/" 始まりならパスとみなす
    first = rest.split()[0] if rest.split() else ""
    path = normalize_path(first) if first.startswith("/") else None
    return {"method": method, "path": path, "raw": s}


def _api_route_keys(entry: PendingEntry) -> list[RouteKey]:
    keys = []
    for ae in entry.api_endpoints:
        path = ae.get("path")
        if not path:
            continue
        method = (ae.get("method") or "ANY").upper()
        keys.append(RouteKey(method, normalize_path(path)))
    return keys


def _nav_route_keys(entry: PendingEntry) -> list[RouteKey]:
    return [RouteKey("ANY", normalize_path(r)) for r in entry.navigate_routes if r]


def _first_api_endpoint_str(entry: PendingEntry) -> str:
    """merged scenario 用の単数 api_endpoint 文字列（合意: 文字列のまま）。"""
    if not entry.api_endpoints:
        return ""
    ae = entry.api_endpoints[0]
    method, path = ae.get("method"), ae.get("path")
    if method and path:
        return f"{method} {path}"
    if path:
        return path
    return ae.get("raw", "") or ""


# --------------------------------------------------------------------------- #
# 事実確認・ユースケース解決
# --------------------------------------------------------------------------- #
@dataclass
class ReconcileFacts:
    controllers: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    pages: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)


def _dedupe(items) -> list:
    seen, out = set(), []
    for x in items:
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _usecase_route_keys(uc: Usecase) -> list[RouteKey]:
    return [
        normalize_route(r)
        for r in (list(uc.related_routes) + list(uc.related_pages))
    ]


def match_existing_usecase(
    entry: PendingEntry, usecases: list[Usecase]
) -> Optional[Usecase]:
    """loop-e2e と同一のルート照合（nav exact > api exact > nav prefix > api prefix）。"""
    nav_keys = _nav_route_keys(entry)
    nav = nav_keys[0] if nav_keys else None
    api_keys = _api_route_keys(entry)

    if nav:
        for uc in usecases:
            if any(route_key_equals(nav, k) for k in _usecase_route_keys(uc)):
                return uc
    for ak in api_keys:
        for uc in usecases:
            if any(route_key_equals(ak, k) for k in _usecase_route_keys(uc)):
                return uc
    if nav:
        for uc in usecases:
            for k in _usecase_route_keys(uc):
                if method_matches(nav.method, k.method) and _path_prefix(nav.path, k.path):
                    return uc
    for ak in api_keys:
        for uc in usecases:
            for k in _usecase_route_keys(uc):
                if method_matches(ak.method, k.method) and _path_prefix(ak.path, k.path):
                    return uc
    return None


def _collect_facts(entry: PendingEntry, checkpoint: dict) -> ReconcileFacts:
    routes = checkpoint.get("routes", [])
    pages = checkpoint.get("pages", [])

    controllers, matched_routes, matched_pages, components = [], [], [], []

    def _find_route(key: RouteKey):
        for r in routes:
            tmpl = RouteKey(
                (r.get("method") or "ANY").upper(), normalize_path(r.get("path", ""))
            )
            if route_key_matches_template(key, tmpl):
                return r
        return None

    for ak in _api_route_keys(entry):
        r = _find_route(ak)
        if r:
            matched_routes.append(
                f'{(r.get("method") or "ANY").upper()} {r.get("path", "")}'
            )
            if r.get("controller"):
                controllers.append(r["controller"])

    for nk in _nav_route_keys(entry):
        for p in pages:
            if path_matches_template(nk.path, normalize_path(p.get("route_path", ""))):
                matched_pages.append(p.get("route_path", ""))
                if p.get("component_name"):
                    components.append(p["component_name"])
                # ページが呼ぶ API → controller へ
                for ac in p.get("api_calls", []):
                    matched_routes.append(ac)
                    r = _find_route(normalize_route(ac))
                    if r and r.get("controller"):
                        controllers.append(r["controller"])
                break

    controllers = _dedupe(controllers)
    entities = _dedupe(
        [re.sub(r"Controller$", "", c) for c in controllers if c]
    )
    return ReconcileFacts(
        controllers=controllers,
        routes=_dedupe(matched_routes),
        pages=_dedupe(matched_pages),
        components=_dedupe(components),
        entities=entities,
    )


def _find_uc_by_facts(
    usecases: list[Usecase], facts: ReconcileFacts
) -> Optional[Usecase]:
    for uc in usecases:
        if facts.controllers and any(
            c in uc.related_controllers for c in facts.controllers
        ):
            return uc
    for uc in usecases:
        if facts.components and any(c in uc.related_views for c in facts.components):
            return uc
    for uc in usecases:
        ucpaths = {normalize_path(x) for x in uc.related_pages}
        if facts.pages and any(normalize_path(p) in ucpaths for p in facts.pages):
            return uc
    for uc in usecases:
        uckeys = _usecase_route_keys(uc)
        for fr in facts.routes:
            fk = normalize_route(fr)
            if any(route_key_equals(fk, k) for k in uckeys):
                return uc
    return None


def _synthesize_usecase(
    entry: PendingEntry, facts: ReconcileFacts, counter: int
) -> Usecase:
    name = (
        facts.components[0]
        if facts.components
        else (entry.scenario_name or (facts.controllers[0] if facts.controllers else entry.loop_e2e_id))
    )
    actor = (entry.steps[0].get("actor") if entry.steps else "") or "ユーザー"
    related_pages = facts.pages or (
        [entry.frontend_url] if entry.frontend_url else []
    )
    return Usecase(
        id=f"UC-LE-{counter:03d}",
        name=name or entry.loop_e2e_id,
        actor=actor,
        description=f"loop-e2e シナリオ「{entry.scenario_name or entry.loop_e2e_id}」から reconcile で生成",
        preconditions=[],
        postconditions=[],
        related_routes=facts.routes,
        related_pages=related_pages,
        related_entities=facts.entities,
        category="loop-e2e",
        priority="medium",
        related_controllers=facts.controllers,
        related_views=facts.components,
        confidence=INFERRED,  # 合成UC: コード証拠で確定していない。sync #2
    )


def resolve_usecase(
    entry: PendingEntry,
    usecases: list[Usecase],
    checkpoint: dict,
    counter: int,
) -> tuple[Usecase, Optional[Usecase]]:
    """(usecase, 新規生成したUC or None) を返す。"""
    uc = match_existing_usecase(entry, usecases)
    if uc:
        return uc, None
    facts = _collect_facts(entry, checkpoint)
    uc = _find_uc_by_facts(usecases, facts)
    if uc:
        return uc, None
    new_uc = _synthesize_usecase(entry, facts, counter)
    return new_uc, new_uc


def _entry_actors(entry: PendingEntry) -> list[str]:
    return _dedupe(
        [str(s.get("actor", "")).strip() for s in entry.steps if str(s.get("actor", "")).strip()]
    )


def detect_conflicts(
    entry: PendingEntry, uc: Usecase, checkpoint: dict
) -> list[Conflict]:
    """既存 UC にマッチした実績が UC 宣言と矛盾するかを決定的に判定する。

    コードを真とし UC は変更しない。検出した矛盾を「要調査」として返す。
    誤検出を抑えるため、根拠が明確な2種のみ判定する:
    - actor_mismatch: 実績ステップのアクターが UC 宣言アクターと一致しない。
    - controller_mismatch: 実績ルートが checkpoint で解決するコントローラが
      UC の related_controllers と1つも重ならない（別ハンドラを叩いている）。
    """
    conflicts: list[Conflict] = []

    actors = _entry_actors(entry)
    if uc.actor and actors and uc.actor not in actors:
        conflicts.append(
            Conflict(
                usecase_id=uc.id,
                kind="actor_mismatch",
                detail=f"UC 宣言アクター「{uc.actor}」と実績アクター {actors} が不一致",
                code_value=uc.actor,
                actual_value=", ".join(actors),
            )
        )

    facts = _collect_facts(entry, checkpoint)
    if facts.controllers and not any(
        c in uc.related_controllers for c in facts.controllers
    ):
        conflicts.append(
            Conflict(
                usecase_id=uc.id,
                kind="controller_mismatch",
                detail=(
                    "実績が叩いたエンドポイントは "
                    f"{facts.controllers} に解決するが、UC の関連コントローラは "
                    f"{uc.related_controllers} で重ならない"
                ),
                code_value=", ".join(uc.related_controllers),
                actual_value=", ".join(facts.controllers),
            )
        )

    return conflicts


def pending_to_scenario(entry: PendingEntry, usecase: Usecase) -> OperationScenario:
    steps = [
        OperationStep(
            step_no=s.get("step_no", i + 1),
            actor=s.get("actor", "ユーザー"),
            action=s.get("action", ""),
            expected_result=s.get("expected_result", ""),
            ui_element=s.get("ui_element", ""),
        )
        for i, s in enumerate(entry.steps)
    ]
    return OperationScenario(
        usecase_id=usecase.id,
        usecase_name=usecase.name,
        scenario_id=f"LE-{entry.loop_e2e_id}",
        scenario_name=entry.scenario_name or entry.loop_e2e_id,
        scenario_type="normal",
        steps=steps,
        variations=[],
        frontend_url=entry.frontend_url or "",
        api_endpoint=_first_api_endpoint_str(entry),
    )


# --------------------------------------------------------------------------- #
# トップレベル reconcile
# --------------------------------------------------------------------------- #
@dataclass
class ReconcileResult:
    reconciled: list[OperationScenario]
    new_usecases: list[Usecase]
    linked: int
    created: int
    conflicts: list[Conflict] = field(default_factory=list)  # 要調査（コードを真）。sync #4
    rescued: list[Usecase] = field(default_factory=list)  # 棄却UCを実績で再昇格。sync #1 follow-on


def _load_usecases(analysis: dict) -> list[Usecase]:
    out = []
    for u in analysis.get("usecases", []):
        out.append(
            Usecase(
                id=u["id"],
                name=u.get("name", ""),
                actor=u.get("actor", ""),
                description=u.get("description", ""),
                preconditions=u.get("preconditions", []),
                postconditions=u.get("postconditions", []),
                related_routes=u.get("related_routes", []),
                related_pages=u.get("related_pages", []),
                related_entities=u.get("related_entities", []),
                category=u.get("category", ""),
                priority=u.get("priority", "medium"),
                related_controllers=u.get("related_controllers", []),
                related_views=u.get("related_views", []),
                confidence=coerce(u.get("confidence")),
            )
        )
    return out


def _max_le_num(usecases: list[Usecase]) -> int:
    nums = []
    for u in usecases:
        m = re.match(r"^UC-LE-(\d+)$", u.id)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else 0


def _norm_name(name: str) -> str:
    return (name or "").strip()


def reconcile(
    analysis: dict,
    pending: dict,
    checkpoint: dict,
    rejected: Optional[list[RejectedUsecase]] = None,
) -> ReconcileResult:
    usecases = _load_usecases(analysis)
    counter = _max_le_num(usecases) + 1

    # 棄却UC を名前で索く（救済用）。棄却UCは証拠アンカーが空なのでルート照合できず、
    # シナリオ名（＝synthesize が付ける名前）との一致で救済する。sync #1 follow-on
    rejected_by_name = {_norm_name(r.name): r for r in (rejected or []) if _norm_name(r.name)}

    entries = [PendingEntry.from_dict(e) for e in pending.get("pending", [])]
    working = list(usecases)
    reconciled, new_usecases = [], []
    conflicts: list[Conflict] = []
    rescued: list[Usecase] = []
    linked = created = 0

    for entry in entries:
        if not entry.loop_e2e_id:
            continue
        uc, created_uc = resolve_usecase(entry, working, checkpoint, counter)
        if created_uc is not None:
            match = rejected_by_name.pop(_norm_name(created_uc.name), None)
            if match is not None:
                # 救済: 棄却UC の id を保持し、実績由来の証拠を付与して derived 確定に再昇格
                uc = replace(created_uc, id=match.id, confidence=DERIVED)
                working.append(uc)
                rescued.append(uc)
            else:
                counter += 1
                new_usecases.append(created_uc)
                working.append(created_uc)
                created += 1
        else:
            linked += 1
            # 既存 UC にマッチ＝静的で確定。実績との矛盾を要調査として記録（コードを真）
            conflicts.extend(detect_conflicts(entry, uc, checkpoint))
        reconciled.append(pending_to_scenario(entry, uc))

    return ReconcileResult(reconciled, new_usecases, linked, created, conflicts, rescued)


def _usecase_to_dict(uc: Usecase) -> dict:
    return {
        "id": uc.id,
        "name": uc.name,
        "actor": uc.actor,
        "description": uc.description,
        "preconditions": uc.preconditions,
        "postconditions": uc.postconditions,
        "related_routes": uc.related_routes,
        "related_pages": uc.related_pages,
        "related_entities": uc.related_entities,
        "related_controllers": uc.related_controllers,
        "related_views": uc.related_views,
        "category": uc.category,
        "priority": uc.priority,
        "confidence": uc.confidence,
    }


def _scenario_to_dict(sc: OperationScenario) -> dict:
    return {
        "scenario_id": sc.scenario_id,
        "usecase_id": sc.usecase_id,
        "usecase_name": sc.usecase_name,
        "scenario_name": sc.scenario_name,
        "scenario_type": sc.scenario_type,
        "frontend_url": sc.frontend_url,
        "api_endpoint": sc.api_endpoint,
        "steps": [
            {
                "step_no": s.step_no,
                "actor": s.actor,
                "action": s.action,
                "expected_result": s.expected_result,
                "ui_element": s.ui_element,
            }
            for s in sc.steps
        ],
        "variations": sc.variations,
    }


def apply_reconcile(analysis: dict, result: ReconcileResult) -> dict:
    """reconcile 結果を analysis dict にマージ（未知トップレベルフィールドは温存）。"""
    uc_data = list(analysis.get("usecases", []))
    existing_ids = {u.get("id") for u in uc_data}
    # 新規UC ＋ 救済UC（棄却から実績由来で再昇格）を確定モデルへ
    for uc in [*result.new_usecases, *result.rescued]:
        if uc.id not in existing_ids:
            uc_data.append(_usecase_to_dict(uc))
            existing_ids.add(uc.id)

    # LE- 出所タグで冪等: 取り込む scenario_id と同じものを除去してから追加
    new_ids = {sc.scenario_id for sc in result.reconciled}
    sc_data = [
        s for s in analysis.get("scenarios", []) if s.get("scenario_id") not in new_ids
    ]
    for sc in result.reconciled:
        sc_data.append(_scenario_to_dict(sc))

    out = dict(analysis)  # 未知トップレベルフィールド温存
    out["usecases"] = uc_data
    out["scenarios"] = sc_data
    md = dict(out.get("metadata", {}))
    md["total_usecases"] = len(uc_data)
    md["total_scenarios"] = len(sc_data)
    out["metadata"] = md
    return out


def validate(analysis: dict) -> None:
    """参照整合性チェック。失敗時は ValueError（呼び出し側は書き戻さないこと）。"""
    uc_ids = {u.get("id") for u in analysis.get("usecases", [])}
    seen = set()
    for s in analysis.get("scenarios", []):
        sid = s.get("scenario_id")
        if sid in seen:
            raise ValueError(f"重複した scenario_id: {sid}")
        seen.add(sid)
        if s.get("usecase_id") not in uc_ids:
            raise ValueError(
                f"dangling usecase_id: {s.get('usecase_id')}（scenario {sid}）"
            )
        for i, st in enumerate(s.get("steps", [])):
            if st.get("step_no") != i + 1:
                raise ValueError(f"step_no が連番でない: {sid}")
