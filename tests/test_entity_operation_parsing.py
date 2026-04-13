"""EntityOperation JSON パースのユニットテスト"""
from analyzer.source_parser import SourceParser, EntityOperation


def test_parse_entity_operations_json_valid():
    """正常なJSONからEntityOperationリストをパースできる"""
    parser = SourceParser()
    text = '''```json
{
  "entity_operations": [
    {
      "entity_class": "Stock",
      "operation": "Update",
      "method_signature": "Stock::where(...)->decrement('qty')",
      "source_file": "app/Services/OrderService.php",
      "source_class": "OrderService",
      "source_method": "createOrder",
      "call_chain": ["OrderController.store", "OrderService.createOrder"]
    },
    {
      "entity_class": "Order",
      "operation": "Create",
      "method_signature": "Order::create([...])",
      "source_file": "app/Services/OrderService.php",
      "source_class": "OrderService",
      "source_method": "createOrder",
      "call_chain": ["OrderController.store", "OrderService.createOrder"]
    }
  ]
}
```'''
    result = parser._parse_entity_operations_json(text)
    assert len(result) == 2
    assert result[0].entity_class == "Stock"
    assert result[0].operation == "Update"
    assert result[0].method_signature == "Stock::where(...)->decrement('qty')"
    assert result[0].source_file == "app/Services/OrderService.php"
    assert result[0].source_class == "OrderService"
    assert result[0].source_method == "createOrder"
    assert result[0].call_chain == ["OrderController.store", "OrderService.createOrder"]
    assert result[1].entity_class == "Order"
    assert result[1].operation == "Create"


def test_parse_entity_operations_json_empty():
    """空の配列のJSONは空リストを返す"""
    parser = SourceParser()
    text = '{"entity_operations": []}'
    result = parser._parse_entity_operations_json(text)
    assert result == []


def test_parse_entity_operations_json_invalid():
    """不正なJSONは空リストを返す"""
    parser = SourceParser()
    result = parser._parse_entity_operations_json("this is not json")
    assert result == []


def test_parse_entity_operations_json_missing_fields():
    """一部フィールドが欠けていてもデフォルト値でパースできる"""
    parser = SourceParser()
    text = '''{"entity_operations": [{"entity_class": "User", "operation": "Read"}]}'''
    result = parser._parse_entity_operations_json(text)
    assert len(result) == 1
    assert result[0].entity_class == "User"
    assert result[0].operation == "Read"
    assert result[0].method_signature == ""
    assert result[0].source_file == ""
    assert result[0].call_chain == []
