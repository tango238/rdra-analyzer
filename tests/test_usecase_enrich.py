"""UsecaseExtractor の related_* 補完（_enrich_controllers / _enrich_pages）テスト"""
from analyzer.source_parser import ParsedPage, ParsedRoute
from analyzer.usecase_extractor import (
    Usecase,
    UsecaseExtractor,
    _api_paths_match,
    _api_path_segments,
)


def _uc(id, related_routes, related_pages=None):
    return Usecase(
        id=id, name=id, actor="ユーザー", description="",
        preconditions=[], postconditions=[],
        related_routes=related_routes, related_pages=related_pages or [],
        related_entities=[], category="", priority="medium",
    )


def _route(method, path, controller):
    return ParsedRoute(method=method, path=path, controller=controller,
                       action="index", middleware=[])


def _page(route_path, component, api_calls):
    return ParsedPage(route_path=route_path, file_path="x.tsx",
                      component_name=component, page_type="list",
                      api_calls=api_calls, imported_hooks=[])


def test_enrich_controllers_matches_method_prefixed_route():
    uc = _uc("UC-001", ["GET /api/v1/hotels"])
    routes = [_route("GET", "/api/v1/hotels", "HotelController")]
    UsecaseExtractor(None)._enrich_controllers([uc], routes)
    assert uc.related_controllers == ["HotelController"]


def test_enrich_controllers_matches_by_path_when_method_differs():
    # related_route が "ANY ..." でも path 一致でコントローラーを引ける
    uc = _uc("UC-001", ["ANY /api/v1/auth"])
    routes = [_route("POST", "/api/v1/auth", "AuthController")]
    UsecaseExtractor(None)._enrich_controllers([uc], routes)
    assert uc.related_controllers == ["AuthController"]


def test_api_paths_match_suffix_with_prefix_difference():
    # frontend は /api/v1 プレフィックスを省く → サフィックス一致
    fe = _api_path_segments("GET /operator/booking/search")
    be = _api_path_segments("GET /api/v1/operator/booking/search")
    assert _api_paths_match(fe, be)


def test_api_paths_match_placeholder():
    fe = _api_path_segments("GET /operator/hotels/:hotelId/bookings")
    be = _api_path_segments("GET /api/v1/operator/hotels/{hotelId}/bookings")
    assert _api_paths_match(fe, be)


def test_api_paths_match_rejects_single_segment_overmatch():
    # 1セグメントのサフィックス過剰一致は弾く
    assert not _api_paths_match(["search"], ["api", "v1", "x", "search"])


def test_api_paths_match_rejects_different_tail():
    assert not _api_paths_match(
        _api_path_segments("/operator/booking/search"),
        _api_path_segments("/api/v1/operator/booking/list"),
    )


def test_enrich_pages_matches_across_prefix_and_placeholder():
    # 実コードベース相当: UC は backend route(/api/v1付き)、page は省略形+:placeholder
    uc = _uc("UC-020", ["GET /api/v1/operator/hotels/{hotelId}/bookings"])
    pages = [_page("/operator/booking/calendar", "BookingCalendar",
                   ["GET /operator/hotels/:hotelId/bookings"])]
    UsecaseExtractor(None)._enrich_pages([uc], pages)
    assert "/operator/booking/calendar" in uc.related_pages


def test_enrich_pages_populates_related_pages_and_views():
    # ページの api_calls が UC の related_route と一致 → related_pages に route_path を入れる
    uc = _uc("UC-010", ["GET /operator/hotels/:hotelId/bookings"])
    pages = [_page("/operator/booking/calendar", "BookingCalendar",
                   ["GET /operator/hotels/:hotelId/bookings"])]
    UsecaseExtractor(None)._enrich_pages([uc], pages)
    assert "/operator/booking/calendar" in uc.related_pages
    assert any("BookingCalendar" in v for v in uc.related_views)


def test_enrich_pages_preserves_existing_llm_pages():
    uc = _uc("UC-010", ["GET /x"], related_pages=["/llm/page"])
    pages = [_page("/derived", "C", ["GET /x"])]
    UsecaseExtractor(None)._enrich_pages([uc], pages)
    assert "/llm/page" in uc.related_pages  # 既存温存
    assert "/derived" in uc.related_pages  # 追加


def test_enrich_pages_no_match_keeps_related_pages_unchanged():
    uc = _uc("UC-010", ["GET /x"], related_pages=["/keep"])
    pages = [_page("/other", "C", ["GET /unrelated"])]
    UsecaseExtractor(None)._enrich_pages([uc], pages)
    assert uc.related_pages == ["/keep"]


def test_enrich_pages_empty_pages_is_noop():
    uc = _uc("UC-010", ["GET /x"], related_pages=["/keep"])
    UsecaseExtractor(None)._enrich_pages([uc], [])
    assert uc.related_pages == ["/keep"]


def test_enrich_pages_is_idempotent():
    uc = _uc("UC-010", ["GET /api/v1/x"])
    pages = [_page("/p", "C", ["GET /x"])]
    UsecaseExtractor(None)._enrich_pages([uc], pages)
    first_pages, first_views = list(uc.related_pages), list(uc.related_views)
    UsecaseExtractor(None)._enrich_pages([uc], pages)  # 2回目
    assert uc.related_pages == first_pages
    assert uc.related_views == first_views


def test_enrich_pages_preserves_existing_related_views():
    # 既存(LLM由来)の related_views は no-match でも温存される
    uc = _uc("UC-010", ["GET /x"])
    uc.related_views = ["LegacyView"]
    pages = [_page("/other", "C", ["GET /unrelated"])]
    UsecaseExtractor(None)._enrich_pages([uc], pages)
    assert "LegacyView" in uc.related_views


# --------------------------------------------------------------------------- #
# from_checkpoint_dict（スキーマdrift耐性）
# --------------------------------------------------------------------------- #
def test_from_checkpoint_dict_filters_unknown_keys():
    from analyzer.source_parser import from_checkpoint_dict
    d = {"method": "GET", "path": "/x", "controller": "C", "action": "i",
         "middleware": [], "prefix": "", "FUTURE_FIELD": "ignored"}
    r = from_checkpoint_dict(ParsedRoute, d)
    assert r.method == "GET" and r.path == "/x"  # 未知キーで落ちない


# --------------------------------------------------------------------------- #
# enrich コマンド: 未知トップレベル/scenarios の温存（round-trip）
# --------------------------------------------------------------------------- #
def test_enrich_command_preserves_unknown_toplevel_and_scenarios(tmp_path, monkeypatch):
    import json
    import main

    uc_dir = tmp_path / "usecases"
    uc_dir.mkdir(parents=True)
    analysis = {
        "metadata": {"total_usecases": 1, "total_scenarios": 1},
        "usecases": [{
            "id": "UC-001", "name": "n", "actor": "ユーザー", "description": "",
            "preconditions": [], "postconditions": [],
            "related_routes": ["GET /api/v1/operator/x"], "related_pages": [],
            "related_entities": [], "related_controllers": [], "related_views": [],
            "category": "", "priority": "medium",
        }],
        "scenarios": [{
            "scenario_id": "LE-x", "usecase_id": "UC-001", "usecase_name": "n",
            "scenario_name": "s", "scenario_type": "normal", "frontend_url": "",
            "api_endpoint": "", "steps": [], "variations": [], "extra_scn": "KEEP2",
        }],
        "custom_top": "KEEP_ME",
    }
    checkpoint = {
        "routes": [{"method": "GET", "path": "/api/v1/operator/x", "controller": "XController",
                    "action": "index", "middleware": []}],
        "pages": [{"route_path": "/x-page", "file_path": "x.tsx", "component_name": "XPage",
                   "page_type": "list", "api_calls": ["GET /operator/x"], "imported_hooks": []}],
    }
    (uc_dir / "analysis_result.json").write_text(
        json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
    (uc_dir / "_checkpoint.json").write_text(
        json.dumps(checkpoint, ensure_ascii=False), encoding="utf-8")

    class _Cfg:
        output_dir = tmp_path
    monkeypatch.setattr(main, "_get_config", lambda: _Cfg())

    main.run_enrich(output_dir=tmp_path)

    out = json.loads((uc_dir / "analysis_result.json").read_text(encoding="utf-8"))
    assert out["custom_top"] == "KEEP_ME"                  # 未知トップレベル温存
    assert out["scenarios"][0]["extra_scn"] == "KEEP2"     # scenario未知フィールド温存
    assert out["scenarios"][0]["scenario_id"] == "LE-x"
    # 補完が効いている
    assert out["usecases"][0]["related_controllers"] == ["XController"]
    assert "/x-page" in out["usecases"][0]["related_pages"]
    assert out["metadata"]["total_scenarios"] == 1
