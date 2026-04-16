"""CrudAnalyzer の EntityOperation 対応テスト"""
from analyzer.source_parser import EntityOperation
from rdra.information_model import Entity
from gap.crud_analyzer import CrudAnalyzer, EntityCrudStatus


def _make_entity(name: str, class_name: str) -> Entity:
    return Entity(
        name=name,
        class_name=class_name,
        attributes=["id", "name"],
    )


def test_check_entity_operations_basic():
    """EntityOperationから基本的なCRUD操作を検出できる"""
    analyzer = CrudAnalyzer()
    status = EntityCrudStatus(entity_name="注文", class_name="Order")
    entity = _make_entity("注文", "Order")
    operations = [
        EntityOperation(
            entity_class="Order", operation="Create",
            method_signature="Order::create([...])",
            source_file="app/Services/OrderService.php",
            source_class="OrderService", source_method="createOrder",
            call_chain=["OrderController.store", "OrderService.createOrder"],
        ),
        EntityOperation(
            entity_class="Order", operation="Read",
            method_signature="Order::find($id)",
            source_file="app/Http/Controllers/OrderController.php",
            source_class="OrderController", source_method="show",
            call_chain=["OrderController.show"],
        ),
    ]
    analyzer._check_entity_operations(status, entity, operations)
    assert status.has_create is True
    assert status.has_read is True
    assert status.has_update is False
    assert status.has_delete is False
    assert "OrderController.store" in status.create_evidence[0]
    assert "OrderController.show" in status.read_evidence[0]


def test_check_entity_operations_indirect():
    """間接的なCRUD操作（別エンティティ経由）を検出できる"""
    analyzer = CrudAnalyzer()
    status = EntityCrudStatus(entity_name="在庫", class_name="Stock")
    entity = _make_entity("在庫", "Stock")
    operations = [
        EntityOperation(
            entity_class="Stock", operation="Update",
            method_signature="Stock::where(...)->decrement('qty')",
            source_file="app/Services/StockService.php",
            source_class="StockService", source_method="decrement",
            call_chain=["OrderController.store", "OrderService.createOrder", "StockService.decrement"],
        ),
        EntityOperation(
            entity_class="Order", operation="Create",
            method_signature="Order::create([...])",
            source_file="app/Services/OrderService.php",
            source_class="OrderService", source_method="createOrder",
            call_chain=["OrderController.store", "OrderService.createOrder"],
        ),
    ]
    analyzer._check_entity_operations(status, entity, operations)
    assert status.has_update is True
    assert status.has_create is False  # Order の Create なので Stock には関係ない
    assert "StockService.decrement" in status.update_evidence[0]


def test_check_entity_operations_collects_all_evidence():
    """同じCRUD操作の全証跡を収集する"""
    analyzer = CrudAnalyzer()
    status = EntityCrudStatus(entity_name="在庫", class_name="Stock")
    entity = _make_entity("在庫", "Stock")
    operations = [
        EntityOperation(
            entity_class="Stock", operation="Update",
            method_signature="Stock::decrement('qty')",
            source_file="", source_class="OrderService", source_method="createOrder",
            call_chain=["OrderController.store", "OrderService.createOrder"],
        ),
        EntityOperation(
            entity_class="Stock", operation="Update",
            method_signature="Stock::increment('qty')",
            source_file="", source_class="ReturnService", source_method="processReturn",
            call_chain=["ReturnController.store", "ReturnService.processReturn"],
        ),
    ]
    analyzer._check_entity_operations(status, entity, operations)
    assert status.has_update is True
    assert len(status.update_evidence) == 2


def test_check_entity_operations_case_insensitive():
    """エンティティクラス名の照合は大文字小文字を区別しない"""
    analyzer = CrudAnalyzer()
    status = EntityCrudStatus(entity_name="ユーザー", class_name="User")
    entity = _make_entity("ユーザー", "User")
    operations = [
        EntityOperation(
            entity_class="user", operation="Read",
            method_signature="User.find()", source_file="", source_class="UserController",
            source_method="show", call_chain=["UserController.show"],
        ),
    ]
    analyzer._check_entity_operations(status, entity, operations)
    assert status.has_read is True


def test_analyze_with_entity_operations():
    """analyze メソッドが entity_operations を受け取って使える"""
    analyzer = CrudAnalyzer()
    entities = [_make_entity("注文", "Order")]
    operations = [
        EntityOperation(
            entity_class="Order", operation="Create",
            method_signature="Order::create([...])", source_file="", source_class="OrderService",
            source_method="createOrder", call_chain=["OrderController.store"],
        ),
    ]
    statuses, gaps = analyzer.analyze(
        entities=entities, routes=[], scenarios=[], usecases=[],
        entity_operations=operations,
    )
    assert len(statuses) == 1
    assert statuses[0].has_create is True
    assert statuses[0].coverage_percentage == 25
    assert len(gaps) == 3
