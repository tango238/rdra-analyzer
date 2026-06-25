"""reconcile モジュールのテスト"""
from reconciliation.reconcile import (
    PendingEntry,
    ReconcileResult,
    RouteKey,
    apply_reconcile,
    match_existing_usecase,
    normalize_path,
    normalize_route,
    path_matches_template,
    pending_to_scenario,
    reconcile,
    resolve_usecase,
    route_key_equals,
    validate,
)
from extraction.usecase_extractor import Usecase


def _uc(id, **kw):
    base = dict(
        name=id,
        actor="ユーザー",
        description="",
        preconditions=[],
        postconditions=[],
        related_routes=[],
        related_pages=[],
        related_entities=[],
        category="",
        priority="medium",
        related_controllers=[],
        related_views=[],
    )
    base.update(kw)
    return Usecase(id=id, **base)


# --------------------------------------------------------------------------- #
# 正規化
# --------------------------------------------------------------------------- #
def test_normalize_path_strips_origin_query_and_trailing_slash():
    assert normalize_path("https://example.com/hotel/?q=1#x") == "/hotel"
    assert normalize_path("/hotel/") == "/hotel"
    assert normalize_path("/") == "/"
    assert normalize_path("hotel") == "/hotel"
    assert normalize_path("") == "/"


def test_normalize_route_strips_method_token():
    assert normalize_route("ANY /api/v1/x") == RouteKey("ANY", "/api/v1/x")
    assert normalize_route("get /api/v1/x/") == RouteKey("GET", "/api/v1/x")
    assert normalize_route("/hotel") == RouteKey("ANY", "/hotel")


def test_route_key_equals_with_any_wildcard():
    assert route_key_equals(RouteKey("ANY", "/x"), RouteKey("GET", "/x"))
    assert route_key_equals(RouteKey("GET", "/x"), RouteKey("GET", "/x"))
    assert not route_key_equals(RouteKey("GET", "/x"), RouteKey("POST", "/x"))
    assert not route_key_equals(RouteKey("GET", "/x"), RouteKey("GET", "/y"))


def test_path_matches_template_with_placeholders():
    assert path_matches_template("/hotels/42/bookings", "/hotels/:id/bookings")
    assert path_matches_template("/hotels/42", "/hotels/{hotelId}")
    assert not path_matches_template("/hotels/42/x", "/hotels/:id")
    assert path_matches_template("/", "/")


# --------------------------------------------------------------------------- #
# 既存UC照合
# --------------------------------------------------------------------------- #
def test_match_existing_usecase_navigate_exact():
    ucs = [_uc("UC-001", related_pages=["/hotel"])]
    entry = PendingEntry(loop_e2e_id="x", navigate_routes=["/hotel"])
    assert match_existing_usecase(entry, ucs).id == "UC-001"


def test_match_existing_usecase_api_against_method_prefixed_route():
    # rdra の related_routes は "METHOD path" 形式
    ucs = [_uc("UC-002", related_routes=["ANY /api/v1/hotels"])]
    entry = PendingEntry(
        loop_e2e_id="x",
        api_endpoints=[{"method": "GET", "path": "/api/v1/hotels", "raw": "..."}],
    )
    assert match_existing_usecase(entry, ucs).id == "UC-002"


def test_match_existing_usecase_none():
    ucs = [_uc("UC-001", related_pages=["/other"])]
    entry = PendingEntry(loop_e2e_id="x", navigate_routes=["/hotel"])
    assert match_existing_usecase(entry, ucs) is None


# --------------------------------------------------------------------------- #
# checkpoint 事実確認・解決
# --------------------------------------------------------------------------- #
def _checkpoint():
    return {
        "routes": [
            {"method": "GET", "path": "/operator/hotels/:hotelId/bookings",
             "controller": "BookingController", "action": "index"},
        ],
        "pages": [
            {"route_path": "/operator/booking/calendar",
             "component_name": "BookingCalendar",
             "api_calls": ["GET /operator/hotels/:hotelId/bookings"]},
        ],
        "controllers": [],
    }


def test_resolve_links_existing_uc_by_controller_via_page_api_calls():
    # nav はページにヒット → ページの api_calls → controller=BookingController
    # 既存UCが related_controllers にそれを持つ → 紐付け（新規生成しない）
    ucs = [_uc("UC-050", related_controllers=["BookingController"])]
    entry = PendingEntry(
        loop_e2e_id="cal", scenario_name="予約カレンダー",
        navigate_routes=["/operator/booking/calendar"],
    )
    uc, created = resolve_usecase(entry, ucs, _checkpoint(), counter=1)
    assert created is None
    assert uc.id == "UC-050"


def test_resolve_synthesizes_new_uc_when_no_match():
    entry = PendingEntry(
        loop_e2e_id="cal", scenario_name="予約カレンダー",
        navigate_routes=["/operator/booking/calendar"],
    )
    uc, created = resolve_usecase(entry, [], _checkpoint(), counter=7)
    assert created is not None
    assert uc.id == "UC-LE-007"
    assert uc.category == "loop-e2e"
    assert "BookingCalendar" in uc.related_views
    assert "BookingController" in uc.related_controllers
    assert "Booking" in uc.related_entities


# --------------------------------------------------------------------------- #
# 変換
# --------------------------------------------------------------------------- #
def test_pending_to_scenario_le_prefix_and_api_string():
    entry = PendingEntry(
        loop_e2e_id="grow-hotel", scenario_name="View hotel page",
        frontend_url="/hotel",
        api_endpoints=[{"method": "GET", "path": "/api/v2/hotels", "raw": "GET ... 200"}],
        steps=[{"step_no": 1, "actor": "ユーザー", "action": "navigate /hotel",
                "expected_result": "loads", "ui_element": "/hotel"}],
    )
    uc = _uc("UC-012", name="ホテル一覧")
    sc = pending_to_scenario(entry, uc)
    assert sc.scenario_id == "LE-grow-hotel"
    assert sc.usecase_id == "UC-012"
    assert sc.scenario_type == "normal"
    assert sc.api_endpoint == "GET /api/v2/hotels"
    assert sc.steps[0].actor == "ユーザー"


def test_pending_api_endpoint_falls_back_to_raw_when_no_method_path():
    entry = PendingEntry(
        loop_e2e_id="x",
        api_endpoints=[{"method": None, "path": None, "raw": "予約APIが成功する"}],
    )
    sc = pending_to_scenario(entry, _uc("UC-001"))
    assert sc.api_endpoint == "予約APIが成功する"


def test_legacy_string_api_endpoint_parsed():
    entry = PendingEntry.from_dict(
        {"loop_e2e_id": "x", "api_endpoints": ["GET /api/v1/hotels returns 200"]}
    )
    assert entry.api_endpoints[0]["method"] == "GET"
    assert entry.api_endpoints[0]["path"] == "/api/v1/hotels"


# --------------------------------------------------------------------------- #
# トップレベル reconcile + merge
# --------------------------------------------------------------------------- #
def _analysis():
    return {
        "metadata": {"total_usecases": 1, "total_scenarios": 0},
        "usecases": [
            {"id": "UC-050", "name": "予約閲覧", "actor": "ユーザー", "description": "",
             "preconditions": [], "postconditions": [], "related_routes": [],
             "related_pages": [], "related_entities": [], "related_controllers": ["BookingController"],
             "related_views": [], "category": "", "priority": "medium"}
        ],
        "scenarios": [],
        "custom_field": "preserve me",
    }


def _pending():
    return {
        "generatedBy": "loop-e2e rdra-export",
        "pending": [
            {"loop_e2e_id": "cal", "scenario_name": "予約カレンダー",
             "frontend_url": "/operator/booking/calendar",
             "navigate_routes": ["/operator/booking/calendar"],
             "api_endpoints": [],
             "steps": [{"step_no": 1, "actor": "ユーザー", "action": "navigate",
                        "expected_result": "ok", "ui_element": "/operator/booking/calendar"}],
             "reason": "no matching usecase by route"},
            {"loop_e2e_id": "newflow", "scenario_name": "新規フロー",
             "frontend_url": "/unknown",
             "navigate_routes": ["/unknown"], "api_endpoints": [],
             "steps": [{"step_no": 1, "actor": "ユーザー", "action": "navigate",
                        "expected_result": "ok", "ui_element": "/unknown"}],
             "reason": "no matching usecase by route"},
        ],
    }


def test_reconcile_links_and_creates():
    result = reconcile(_analysis(), _pending(), _checkpoint())
    assert result.linked == 1  # cal → UC-050 (controller)
    assert result.created == 1  # newflow → 新規UC
    assert len(result.reconciled) == 2
    assert {s.scenario_id for s in result.reconciled} == {"LE-cal", "LE-newflow"}


def test_apply_reconcile_recomputes_metadata_and_preserves_unknown():
    analysis = _analysis()
    result = reconcile(analysis, _pending(), _checkpoint())
    out = apply_reconcile(analysis, result)
    assert out["custom_field"] == "preserve me"  # 未知フィールド温存
    assert out["metadata"]["total_scenarios"] == 2
    assert out["metadata"]["total_usecases"] == 2  # 元1 + 新規1
    validate(out)  # 参照整合OK


def test_reconcile_is_idempotent():
    analysis = _analysis()
    out1 = apply_reconcile(analysis, reconcile(analysis, _pending(), _checkpoint()))
    # 2回目: 同じ pending を再取り込みしても scenario が重複しない
    out2 = apply_reconcile(out1, reconcile(out1, _pending(), _checkpoint()))
    le_ids = [s["scenario_id"] for s in out2["scenarios"] if s["scenario_id"].startswith("LE-")]
    assert sorted(le_ids) == ["LE-cal", "LE-newflow"]
    validate(out2)


def test_le_scenarios_preserved_and_non_le_untouched():
    analysis = _analysis()
    analysis["scenarios"].append(
        {"scenario_id": "SC-001-01", "usecase_id": "UC-050", "usecase_name": "予約閲覧",
         "scenario_name": "既存", "scenario_type": "normal", "frontend_url": "",
         "api_endpoint": "", "steps": [], "variations": []}
    )
    out = apply_reconcile(analysis, reconcile(analysis, _pending(), _checkpoint()))
    ids = {s["scenario_id"] for s in out["scenarios"]}
    assert "SC-001-01" in ids  # 非LEは温存
    assert "LE-cal" in ids and "LE-newflow" in ids


# --------------------------------------------------------------------------- #
# validate
# --------------------------------------------------------------------------- #
def test_validate_detects_dangling_usecase_id():
    bad = {"usecases": [{"id": "UC-001"}],
           "scenarios": [{"scenario_id": "LE-x", "usecase_id": "UC-999", "steps": []}]}
    try:
        validate(bad)
        assert False, "should raise"
    except ValueError as e:
        assert "dangling" in str(e)


def test_validate_detects_duplicate_scenario_id():
    bad = {"usecases": [{"id": "UC-001"}],
           "scenarios": [
               {"scenario_id": "LE-x", "usecase_id": "UC-001", "steps": []},
               {"scenario_id": "LE-x", "usecase_id": "UC-001", "steps": []},
           ]}
    try:
        validate(bad)
        assert False, "should raise"
    except ValueError as e:
        assert "重複" in str(e)


def test_validate_detects_non_sequential_step_no():
    bad = {"usecases": [{"id": "UC-001"}],
           "scenarios": [{"scenario_id": "LE-x", "usecase_id": "UC-001",
                          "steps": [{"step_no": 2}]}]}
    try:
        validate(bad)
        assert False, "should raise"
    except ValueError as e:
        assert "連番" in str(e)
