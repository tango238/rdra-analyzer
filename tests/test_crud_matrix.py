"""
tests/test_crud_matrix.py — crud_matrix モジュールのユニットテスト (18 cases)

TDD: まず RED で全件書き、crud_matrix.py 実装で GREEN にする。
"""

import pytest
from analyzer.source_parser import EntityOperation, ParsedRoute
from analyzer.usecase_extractor import Usecase

from rdra.crud_matrix import (
    VERB_TO_CRUD,
    compute_uc_entity_crud,
    build_uc_entity_crud_index,
    _build_routes_index,
    _tokenize,
    _normalize_op_to_chars,
)


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _make_uc(uc_id: str, name: str, routes: list[str], entities: list[str]) -> Usecase:
    return Usecase(
        id=uc_id,
        name=name,
        actor="User",
        description="",
        preconditions=[],
        postconditions=[],
        related_routes=routes,
        related_pages=[],
        related_entities=entities,
        category="",
    )


def _make_route(method: str, path: str, controller: str, action: str) -> ParsedRoute:
    return ParsedRoute(
        method=method,
        path=path,
        controller=controller,
        action=action,
        middleware=[],
    )


def _make_op(
    entity_class: str,
    operation: str,
    source_class: str = "",
    source_method: str = "",
    call_chain: list[str] | None = None,
) -> EntityOperation:
    return EntityOperation(
        entity_class=entity_class,
        operation=operation,
        method_signature="",
        source_file="",
        source_class=source_class,
        source_method=source_method,
        call_chain=call_chain or [],
    )


# ---------------------------------------------------------------------------
# Tier 1: entity_operations マッチ
# ---------------------------------------------------------------------------

class TestTier1:
    def test_tier1_entity_operations_match(self):
        """call_chain[0] が UC の controller.action と一致 → CRUD 集約"""
        uc = _make_uc("UC-001", "ユーザー登録", ["POST /api/users"], ["User"])
        route = _make_route("POST", "/api/users", "UserController", "store")
        routes_by_key = _build_routes_index([route])
        op = _make_op("User", "Create", call_chain=["UserController.store"])

        result = compute_uc_entity_crud(uc, "User", [op], routes_by_key)
        assert result == {"C"}

    def test_tier1_entity_class_filter(self):
        """別 entity_class の操作は除外 → Tier 1 不発で Tier 2 にフォールバック"""
        uc = _make_uc("UC-001", "ユーザー登録", ["POST /api/users"], ["User"])
        route = _make_route("POST", "/api/users", "UserController", "store")
        routes_by_key = _build_routes_index([route])
        # Order の操作なので User に対する Tier 1 には一致しない
        op_order = _make_op("Order", "Create", call_chain=["UserController.store"])
        op_user = _make_op("User", "Read", call_chain=["UserController.store"])

        # User の Tier 1 は op_user の Read のみ (op_order は除外)
        result = compute_uc_entity_crud(uc, "User", [op_order, op_user], routes_by_key)
        assert "R" in result
        # op_order の Create は User には適用されない
        assert "C" not in result

    def test_tier1_multiple_operations_aggregated(self):
        """Create と Update 両方ある場合は両方返す"""
        uc = _make_uc("UC-002", "注文処理", ["POST /api/orders"], ["Order"])
        route = _make_route("POST", "/api/orders", "OrderController", "store")
        routes_by_key = _build_routes_index([route])
        ops = [
            _make_op("Order", "Create", call_chain=["OrderController.store"]),
            _make_op("Order", "Update", call_chain=["OrderController.store"]),
        ]

        result = compute_uc_entity_crud(uc, "Order", ops, routes_by_key)
        assert result == {"C", "U"}

    def test_tier1_create_update_split(self):
        """'Create/Update' は C と U に分解される"""
        uc = _make_uc("UC-003", "在庫更新", ["PUT /api/stock"], ["Stock"])
        route = _make_route("PUT", "/api/stock", "StockController", "upsert")
        routes_by_key = _build_routes_index([route])
        op = _make_op("Stock", "Create/Update", call_chain=["StockController.upsert"])

        result = compute_uc_entity_crud(uc, "Stock", [op], routes_by_key)
        assert result == {"C", "U"}


# ---------------------------------------------------------------------------
# Tier 2: 動詞ヒューリスティック
# ---------------------------------------------------------------------------

class TestTier2:
    def test_tier2_verb_update(self):
        """update/updated/edit 等が U"""
        uc = _make_uc("UC-010", "パスワード再設定", ["POST /api/auth/updated"], ["User"])
        route = _make_route("POST", "/api/auth/updated", "AuthController", "updated")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "User", [], routes_by_key)
        assert "U" in result

    def test_tier2_verb_delete(self):
        """destroy/delete/remove 等が D"""
        uc = _make_uc("UC-011", "ユーザー削除", ["DELETE /api/users/1"], ["User"])
        route = _make_route("DELETE", "/api/users/1", "UserController", "destroy")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "User", [], routes_by_key)
        assert "D" in result

    def test_tier2_verb_create(self):
        """create/store/register 等が C"""
        uc = _make_uc("UC-012", "ユーザー登録", ["POST /api/users"], ["User"])
        route = _make_route("POST", "/api/users", "UserController", "store")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "User", [], routes_by_key)
        assert "C" in result

    def test_tier2_verb_read(self):
        """show/index/list 等が R"""
        uc = _make_uc("UC-013", "ユーザー一覧", ["GET /api/users"], ["User"])
        route = _make_route("GET", "/api/users", "UserController", "index")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "User", [], routes_by_key)
        assert "R" in result

    def test_tier2_camelcase_action(self):
        """passwordUpdate → U"""
        uc = _make_uc("UC-014", "パスワード変更", ["PUT /api/password"], ["User"])
        route = _make_route("PUT", "/api/password", "AuthController", "passwordUpdate")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "User", [], routes_by_key)
        assert "U" in result

    def test_tier2_snake_case_action(self):
        """password_reset → U"""
        uc = _make_uc("UC-015", "パスワードリセット", ["POST /api/password-reset"], ["User"])
        route = _make_route("POST", "/api/password-reset", "AuthController", "password_reset")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "User", [], routes_by_key)
        assert "U" in result

    def test_tier2_token_match_documents_known_overreach(self):
        """updateLog → ["update","log"] → update ヒット → U (仕様として明示)"""
        uc = _make_uc("UC-016", "ログ更新", ["PUT /api/logs"], ["Log"])
        route = _make_route("PUT", "/api/logs", "LogController", "updateLog")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "Log", [], routes_by_key)
        assert "U" in result

    def test_tier2_no_substring_false_positive(self):
        """updates_count → ["updates","count"] → updates は辞書未登録 → U にならない"""
        uc = _make_uc("UC-017", "カウント取得", ["GET /api/count"], ["Counter"])
        route = _make_route("GET", "/api/count", "CounterController", "updates_count")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "Counter", [], routes_by_key)
        assert "U" not in result


# ---------------------------------------------------------------------------
# Tier 3: HTTP メソッドフォールバック
# ---------------------------------------------------------------------------

class TestTier3:
    def test_tier3_http_method_fallback(self):
        """tier1/2 不発時 HTTP メソッドベース"""
        uc = _make_uc("UC-020", "データ送信", ["POST /api/webhook"], ["Webhook"])
        route = _make_route("POST", "/api/webhook", "WebhookController", "handle")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "Webhook", [], routes_by_key)
        # "handle" は辞書に無い → Tier 3: POST → C
        assert "C" in result


# ---------------------------------------------------------------------------
# UC-019 回帰テスト
# ---------------------------------------------------------------------------

class TestUC019Regression:
    def test_uc019_password_reset_returns_update(self):
        """UC-019 パスワード再設定で User が U と表示される回帰テスト"""
        uc = _make_uc(
            "UC-019",
            "パスワード再設定",
            [
                "POST /api/v2/spotly/auth/remind",
                "POST /api/v2/spotly/auth/updated",
            ],
            ["User", "SpotlyCustomer"],
        )
        routes = [
            _make_route(
                "POST", "/api/v2/spotly/auth/remind",
                "Spotly\\Auth\\PasswordReminder\\ApiController", "remind",
            ),
            _make_route(
                "POST", "/api/v2/spotly/auth/updated",
                "Spotly\\Auth\\PasswordReminder\\ApiController", "updated",
            ),
        ]
        routes_by_key = _build_routes_index(routes)

        result = compute_uc_entity_crud(uc, "User", [], routes_by_key)
        assert "U" in result
        # POST だけなら C になるが Tier 2 で "remind" → U, "updated" → U
        assert "C" not in result


# ---------------------------------------------------------------------------
# エッジケース
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_uc_with_no_routes_returns_empty(self):
        """関連ルート無し → 空 set"""
        uc = _make_uc("UC-030", "概要閲覧", [], ["Dashboard"])
        result = compute_uc_entity_crud(uc, "Dashboard", [], {})
        assert result == set()

    def test_priority_tier1_skips_tier2(self):
        """tier1 で結果が出れば tier2 は実行しない"""
        uc = _make_uc("UC-040", "ユーザー更新", ["PUT /api/users"], ["User"])
        route = _make_route("PUT", "/api/users", "UserController", "destroy")
        routes_by_key = _build_routes_index([route])
        # entity_operations は Update と言っている
        op = _make_op("User", "Update", call_chain=["UserController.destroy"])

        result = compute_uc_entity_crud(uc, "User", [op], routes_by_key)
        # Tier 1 が U を返す。action="destroy" の Tier 2 D は無視される
        assert result == {"U"}

    def test_priority_tier2_skips_tier3(self):
        """tier2 で結果が出れば tier3 は実行しない"""
        uc = _make_uc("UC-041", "パスワード再設定", ["POST /api/auth/reset"], ["User"])
        route = _make_route("POST", "/api/auth/reset", "AuthController", "reset")
        routes_by_key = _build_routes_index([route])

        result = compute_uc_entity_crud(uc, "User", [], routes_by_key)
        # Tier 2: "reset" → U。Tier 3 の POST→C には落ちない
        assert result == {"U"}


# ---------------------------------------------------------------------------
# build_uc_entity_crud_index (一括計算)
# ---------------------------------------------------------------------------

class TestBuildIndex:
    def test_build_index_full_pipeline(self):
        """build_uc_entity_crud_index が全 UC × Entity を一括計算"""
        usecases = [
            _make_uc("UC-001", "登録", ["POST /api/users"], ["User"]),
            _make_uc("UC-002", "一覧", ["GET /api/users"], ["User"]),
        ]
        routes = [
            _make_route("POST", "/api/users", "UserController", "store"),
            _make_route("GET", "/api/users", "UserController", "index"),
        ]
        ops = [
            _make_op("User", "Create", call_chain=["UserController.store"]),
        ]

        index = build_uc_entity_crud_index(usecases, ops, routes)

        assert index["UC-001"]["User"] == ["C"]
        assert index["UC-002"]["User"] == ["R"]


# ---------------------------------------------------------------------------
# ユーティリティ関数
# ---------------------------------------------------------------------------

class TestUtils:
    @pytest.mark.parametrize("text,expected", [
        ("passwordUpdate", ["password", "update"]),
        ("password_reset", ["password", "reset"]),
        ("PASSWORD_RESET", ["password", "reset"]),
        ("kebab-case-name", ["kebab", "case", "name"]),
        ("/api/v2/users/destroy", ["api", "v2", "users", "destroy"]),
        ("XMLParser", ["xml", "parser"]),
        ("getHTTPResponse", ["get", "http", "response"]),
    ])
    def test_tokenize(self, text, expected):
        assert _tokenize(text) == expected

    @pytest.mark.parametrize("operation,expected", [
        ("Create", ["C"]),
        ("Read", ["R"]),
        ("Update", ["U"]),
        ("Delete", ["D"]),
        ("Create/Update", ["C", "U"]),
        ("Read/Update", ["R", "U"]),
    ])
    def test_normalize_op_to_chars(self, operation, expected):
        assert _normalize_op_to_chars(operation) == expected
