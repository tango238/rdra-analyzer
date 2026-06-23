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
