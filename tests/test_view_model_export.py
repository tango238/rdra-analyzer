"""表示契約 view-model 出力のテスト — @rdra/viewer 切り出し（divergence #8 / contexts+mapping formalize）。

`_render_viewer` は viewer.html の埋め込み DATA と完全に同一形状の `rdra-view-model.json`
（内部 Published Language）を併せて出力する。Core はこれを吐くだけ、切り出し後の
@rdra/viewer はこの JSON のみを入力に描画する（dumb renderer）。
"""

import json

from extraction.usecase_extractor import UseCase
from visualization.mermaid_renderer import MermaidRenderer, VIEW_MODEL_SCHEMA_VERSION


def _uc(**kw) -> UseCase:
    base = dict(
        id="UC-001",
        name="予約を確定する",
        actor="オーナー",
        description="",
        preconditions=[],
        postconditions=[],
        related_routes=["POST /reservations/:id/place"],
        related_pages=["/reservations/:id"],
        related_entities=["Reservation"],
        category="予約管理",
    )
    base.update(kw)
    return UseCase(**base)  # type: ignore[arg-type]


def _render(tmp_path, **overrides):
    """_render_viewer は self._* を使わずに引数から DATA を組むため、ジェネレータは None で良い。"""
    renderer = MermaidRenderer(None, None, None)  # type: ignore[arg-type]
    kwargs = dict(
        entities=[],
        relationships=[],
        usecases=[_uc()],
        scenarios=[],
        groups=[],
        state_machines=[],
        policies=[],
        mermaid_sources={"information_model": "erDiagram\n"},
        rdra_dir=tmp_path,
        entity_operations=[],
        routes=[],
    )
    kwargs.update(overrides)
    renderer._render_viewer(**kwargs)
    return tmp_path / "rdra-view-model.json"


class TestViewModelExport:
    def test_emits_view_model_json_alongside_html(self, tmp_path) -> None:
        vm_path = _render(tmp_path)
        assert vm_path.exists()
        assert (tmp_path / "viewer.html").exists()  # 既存の出力は維持

    def test_view_model_has_contract_wrapper(self, tmp_path) -> None:
        vm = json.loads(_render(tmp_path).read_text(encoding="utf-8"))
        assert vm["schemaVersion"] == VIEW_MODEL_SCHEMA_VERSION
        assert "generated_at" in vm
        assert vm["mermaid_sources"] == {"information_model": "erDiagram\n"}

    def test_view_model_carries_all_data_keys(self, tmp_path) -> None:
        vm = json.loads(_render(tmp_path).read_text(encoding="utf-8"))
        expected = {
            "entities", "relationships", "usecases", "scenarios",
            "state_machines", "policies", "information_groups",
            "screen_specs", "entity_operations", "uc_entity_crud",
        }
        assert expected.issubset(vm.keys())
        assert len(vm["usecases"]) == 1
        assert vm["usecases"][0]["id"] == "UC-001"

    def test_embedded_html_data_matches_view_model(self, tmp_path) -> None:
        """埋め込み DATA（viewer.html）と契約 JSON の DATA 部分が一致する（レイアウト現状維持の保証）。"""
        vm_path = _render(tmp_path)
        vm = json.loads(vm_path.read_text(encoding="utf-8"))
        html = (tmp_path / "viewer.html").read_text(encoding="utf-8")
        # DATA 部分（wrapper 3 キーを除く）が viewer.html に埋め込まれた JSON と同一であること
        data_part = {
            k: v for k, v in vm.items()
            if k not in ("schemaVersion", "generated_at", "mermaid_sources")
        }
        embedded = json.dumps(data_part, ensure_ascii=False)
        assert embedded in html
