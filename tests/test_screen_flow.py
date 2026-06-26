"""画面遷移階層グラフ生成のテスト — 画面 × loop-e2e 実走シナリオの Projection。"""

from extraction.derived.screen_flow import (
    ScreenFlowGenerator,
    _match_page,
    _is_forward,
    _route_from_step,
)


def _screen(route, title="", parent="", children=None, buttons=None, nav=None):
    return {
        "route_path": route,
        "page_title": title or route,
        "parent_page": parent,
        "child_pages": children or [],
        "action_buttons": [{"label": l, "target": t} for l, t in (buttons or [])],
        "shared_nav_items": [{"label": "", "target": t} for t in (nav or [])],
    }


def _scenario(sid, steps):
    return {
        "scenario_id": sid,
        "usecase_id": "UC-001",
        "steps": [
            {"step_no": i + 1, "action": a, "ui_element": u}
            for i, (a, u) in enumerate(steps)
        ],
    }


class TestHelpers:
    def test_match_page_exact(self):
        assert _match_page("/reservations", ["/reservations", "/users"]) == "/reservations"

    def test_match_page_placeholder(self):
        assert _match_page("/reservations/rsv_2", ["/reservations/:id"]) == "/reservations/:id"

    def test_match_page_no_match(self):
        assert _match_page("/facility/rooms/101/out", ["/facility", "/reservations/:id"]) is None

    def test_is_forward_drilldown(self):
        assert _is_forward("/reservations", "/reservations/new") is True

    def test_is_forward_backlink_false(self):
        assert _is_forward("/reservations/new", "/reservations") is False

    def test_route_from_step_href(self):
        assert _route_from_step("click a[href='/reservations/rsv_2']", "a[href='/reservations/rsv_2']") == "/reservations/rsv_2"

    def test_route_from_step_navigate_absolute(self):
        assert _route_from_step("navigate http://127.0.0.1:3000/dashboard", "http://127.0.0.1:3000/dashboard") == "/dashboard"


class TestScreenFlow:
    def test_empty_returns_placeholder(self):
        out = ScreenFlowGenerator().generate_mermaid([], [])
        assert "flowchart TD" in out
        assert "画面データがありません" in out

    def test_login_to_dashboard_entry(self):
        screens = [_screen("/login", "ログイン"), _screen("/dashboard", "ダッシュボード", buttons=[("ログイン", "/dashboard")])]
        out = ScreenFlowGenerator().generate_mermaid(screens, [])
        assert "flowchart TD" in out
        assert "s_login" in out and "s_dashboard" in out
        assert "ログイン" in out

    def test_nav_backbone_from_dashboard(self):
        screens = [
            _screen("/dashboard", "D", nav=["/dashboard", "/reservations", "/users", "/logout"]),
            _screen("/reservations", "予約一覧"),
            _screen("/users", "ユーザー"),
        ]
        out = ScreenFlowGenerator().generate_mermaid(screens, [])
        # dashboard から各セクションへの nav エッジ（点線）
        assert "s_dashboard -.-> s_reservations" in out
        assert "s_dashboard -.-> s_users" in out

    def test_drilldown_with_button_label(self):
        screens = [
            _screen("/reservations", "予約一覧", buttons=[("＋ 予約を作成", "/reservations/new")]),
            _screen("/reservations/new", "予約を作成", parent="/reservations"),
        ]
        out = ScreenFlowGenerator().generate_mermaid(screens, [])
        assert "s_reservations --> " in out or "s_reservations -->|" in out
        assert "予約を作成" in out

    def test_observed_edge_highlighted(self):
        screens = [
            _screen("/reservations", "予約一覧"),
            _screen("/reservations/:id", "予約詳細"),
        ]
        scenarios = [_scenario("LE-x", [
            ("navigate /reservations", "/reservations"),
            ("click a[href='/reservations/rsv_2']", "a[href='/reservations/rsv_2']"),
        ])]
        out = ScreenFlowGenerator().generate_mermaid(screens, scenarios)
        # 実走として強調（太線 linkStyle + ✓実走ラベル）
        assert "✓実走" in out
        assert "linkStyle" in out and "stroke-width:3px" in out

    def test_placeholder_route_maps_to_template_node(self):
        screens = [_screen("/reservations", "一覧"), _screen("/reservations/:id", "詳細")]
        scenarios = [_scenario("LE-y", [
            ("navigate /reservations", "/reservations"),
            ("click a[href='/reservations/rsv_1']", "a[href='/reservations/rsv_1']"),
        ])]
        out = ScreenFlowGenerator().generate_mermaid(screens, scenarios)
        # 具体値 rsv_1 ではなくテンプレ :id ノードへ集約される
        assert "s_reservations_:id" not in out  # slug は : を除去
        assert "s_reservations" in out
        assert "rsv_1" not in out
