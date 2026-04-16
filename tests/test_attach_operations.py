"""_attach_operations_to_controllers のユニットテスト"""
from analyzer.source_parser import (
    SourceParser, ParsedController, EntityOperation,
)


def _make_controller(class_name: str, methods: list[str]) -> ParsedController:
    return ParsedController(
        class_name=class_name,
        file_path="",
        namespace="",
        methods=methods,
        docblocks={},
        request_rules={},
    )


def test_attach_single_operation():
    """単一のEntityOperationがコントローラーに紐付く"""
    parser = SourceParser()
    controllers = [_make_controller("OrderController", ["store", "index"])]
    operations = [
        EntityOperation(
            entity_class="Order",
            operation="Create",
            method_signature="Order::create([...])",
            source_file="app/Services/OrderService.php",
            source_class="OrderService",
            source_method="createOrder",
            call_chain=["OrderController.store", "OrderService.createOrder"],
        ),
    ]
    parser._attach_operations_to_controllers(controllers, operations)
    assert "store" in controllers[0].entity_operations
    assert len(controllers[0].entity_operations["store"]) == 1
    assert controllers[0].entity_operations["store"][0].entity_class == "Order"


def test_attach_multiple_operations_same_method():
    """同じメソッドに複数のEntityOperationが紐付く"""
    parser = SourceParser()
    controllers = [_make_controller("OrderController", ["store"])]
    operations = [
        EntityOperation(
            entity_class="Order", operation="Create",
            method_signature="Order::create", source_file="", source_class="OrderService",
            source_method="createOrder", call_chain=["OrderController.store", "OrderService.createOrder"],
        ),
        EntityOperation(
            entity_class="Stock", operation="Update",
            method_signature="Stock::decrement", source_file="", source_class="StockService",
            source_method="decrement", call_chain=["OrderController.store", "OrderService.createOrder", "StockService.decrement"],
        ),
    ]
    parser._attach_operations_to_controllers(controllers, operations)
    assert len(controllers[0].entity_operations["store"]) == 2


def test_attach_no_matching_controller():
    """マッチするコントローラーがない場合、何も紐付かない"""
    parser = SourceParser()
    controllers = [_make_controller("UserController", ["index"])]
    operations = [
        EntityOperation(
            entity_class="Order", operation="Create",
            method_signature="Order::create", source_file="", source_class="OrderService",
            source_method="createOrder", call_chain=["OrderController.store"],
        ),
    ]
    parser._attach_operations_to_controllers(controllers, operations)
    assert controllers[0].entity_operations == {}


def test_attach_empty_call_chain():
    """call_chainが空のEntityOperationは紐付けをスキップする"""
    parser = SourceParser()
    controllers = [_make_controller("OrderController", ["store"])]
    operations = [
        EntityOperation(
            entity_class="Order", operation="Create",
            method_signature="Order::create", source_file="", source_class="OrderService",
            source_method="createOrder", call_chain=[],
        ),
    ]
    parser._attach_operations_to_controllers(controllers, operations)
    assert controllers[0].entity_operations == {}
