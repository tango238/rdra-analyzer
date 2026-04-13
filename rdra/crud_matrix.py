"""
rdra/crud_matrix.py — UC × Entity の CRUD 判定モジュール

多段フォールバックで CRUD セットを決定する:
  Tier 1: entity_operations (LLM 抽出結果) から照合
  Tier 2: コントローラー action / パストークンの動詞ヒューリスティック
  Tier 3: HTTP メソッドベース (フォールバック)
"""

from __future__ import annotations

import re

from analyzer.source_parser import EntityOperation, ParsedRoute
from analyzer.usecase_extractor import Usecase

# ---------------------------------------------------------------------------
# 動詞 → CRUD 辞書 (Tier 2)
# ---------------------------------------------------------------------------

VERB_TO_CRUD: dict[str, str] = {
    # Update 系
    "update": "U", "updated": "U", "edit": "U", "change": "U",
    "modify": "U", "save": "U", "patch": "U", "renew": "U",
    "reset": "U", "remind": "U",
    # Delete 系
    "delete": "D", "destroy": "D", "remove": "D", "cancel": "D",
    # Create 系
    "create": "C", "store": "C", "add": "C", "register": "C",
    "signup": "C", "new": "C",
    # Read 系
    "show": "R", "index": "R", "list": "R", "get": "R",
    "find": "R", "search": "R", "view": "R",
}

# HTTP メソッド → CRUD (Tier 3)
_HTTP_METHOD_TO_CRUD: dict[str, str] = {
    "POST": "C",
    "GET": "R",
    "PUT": "U",
    "PATCH": "U",
    "DELETE": "D",
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_uc_entity_crud(
    uc: Usecase,
    entity_class: str,
    entity_operations: list[EntityOperation],
    routes_by_key: dict[str, ParsedRoute],
) -> set[str]:
    """UC × Entity の CRUD セットを多段フォールバックで判定して返す。"""

    if not uc.related_routes:
        return set()

    # Tier 1: entity_operations から照合
    tier1 = _tier1_entity_ops(uc, entity_class, entity_operations, routes_by_key)
    if tier1:
        return tier1

    # Tier 2: 動詞ヒューリスティック
    tier2 = _tier2_verb_heuristics(uc, routes_by_key)
    if tier2:
        return tier2

    # Tier 3: HTTP メソッドフォールバック
    return _tier3_http_method(uc)


def build_uc_entity_crud_index(
    usecases: list[Usecase],
    entity_operations: list[EntityOperation],
    routes: list[ParsedRoute],
) -> dict[str, dict[str, list[str]]]:
    """全 UC × 全関連 Entity の CRUD を一括計算する。

    Returns: {uc_id: {entity_class: ["C","U", ...]}}
    """
    routes_by_key = _build_routes_index(routes)
    index: dict[str, dict[str, list[str]]] = {}

    for uc in usecases:
        uc_map: dict[str, list[str]] = {}
        for entity_class in uc.related_entities:
            crud_set = compute_uc_entity_crud(
                uc, entity_class, entity_operations, routes_by_key,
            )
            if crud_set:
                uc_map[entity_class] = sorted(crud_set)
        if uc_map:
            index[uc.id] = uc_map

    return index


# ---------------------------------------------------------------------------
# Index builder
# ---------------------------------------------------------------------------


def _build_routes_index(routes: list[ParsedRoute]) -> dict[str, ParsedRoute]:
    """{"METHOD PATH": ParsedRoute} の dict を構築。"""
    return {f"{r.method} {r.path}": r for r in routes}


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# camelCase 境界: 小文字→大文字、または連続大文字→大文字+小文字
_CAMEL_RE = re.compile(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _tokenize(text: str) -> list[str]:
    """camelCase / snake_case / kebab-case / path を小文字 token のリストに分解。"""
    # パス区切り・snake_case・kebab-case で分割
    parts = re.split(r"[/_\-]+", text.strip("/"))
    tokens: list[str] = []
    for part in parts:
        if not part:
            continue
        # camelCase / PascalCase を分割
        sub_tokens = _CAMEL_RE.sub("_", part).split("_")
        tokens.extend(t.lower() for t in sub_tokens if t)
    return tokens


# ---------------------------------------------------------------------------
# Operation normalizer
# ---------------------------------------------------------------------------


def _normalize_op_to_chars(operation: str) -> list[str]:
    """'Create' → ['C'], 'Create/Update' → ['C', 'U']"""
    mapping = {"Create": "C", "Read": "R", "Update": "U", "Delete": "D"}
    return [mapping[op.strip()] for op in operation.split("/") if op.strip() in mapping]


# ---------------------------------------------------------------------------
# Tier implementations
# ---------------------------------------------------------------------------


def _tier1_entity_ops(
    uc: Usecase,
    entity_class: str,
    entity_operations: list[EntityOperation],
    routes_by_key: dict[str, ParsedRoute],
) -> set[str]:
    """Tier 1: entity_operations のうち、call_chain[0] が UC の関連ルートの
    controller.action と一致し、かつ entity_class 一致するものを集約。"""

    # UC の関連ルートから controller.action のセットを構築
    uc_controller_actions: set[str] = set()
    for route_str in uc.related_routes:
        route = routes_by_key.get(route_str)
        if route:
            uc_controller_actions.add(f"{route.controller}.{route.action}")

    if not uc_controller_actions:
        return set()

    crud_chars: set[str] = set()
    for op in entity_operations:
        if op.entity_class != entity_class:
            continue
        if not op.call_chain:
            continue
        if op.call_chain[0] in uc_controller_actions:
            crud_chars.update(_normalize_op_to_chars(op.operation))

    return crud_chars


def _tier2_verb_heuristics(
    uc: Usecase,
    routes_by_key: dict[str, ParsedRoute],
) -> set[str]:
    """Tier 2: action 名やパス末尾をトークン化し VERB_TO_CRUD で照合。"""
    crud_chars: set[str] = set()

    for route_str in uc.related_routes:
        route = routes_by_key.get(route_str)
        if route:
            # action をトークン化
            tokens = _tokenize(route.action)
        else:
            # 逆引き不発時はパス末尾セグメントをトークン化
            parts = route_str.split()
            path = parts[1] if len(parts) > 1 else parts[0]
            tokens = _tokenize(path.split("/")[-1]) if "/" in path else []

        for token in tokens:
            if token in VERB_TO_CRUD:
                crud_chars.add(VERB_TO_CRUD[token])

    return crud_chars


def _tier3_http_method(uc: Usecase) -> set[str]:
    """Tier 3: HTTP メソッドベースのフォールバック。"""
    crud_chars: set[str] = set()

    for route_str in uc.related_routes:
        parts = route_str.split()
        if parts:
            method = parts[0].upper()
            if method in _HTTP_METHOD_TO_CRUD:
                crud_chars.add(_HTTP_METHOD_TO_CRUD[method])

    return crud_chars
