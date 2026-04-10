# Entity-First CRUD Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace surface-level HTTP-method CRUD detection with entity-source-code-driven bottom-up analysis that traces call chains from models back to controllers.

**Architecture:** Add an `EntityOperation` dataclass and a new LLM extraction step in `source_parser.py` that reads entity model code and traces CRUD operations back through service/repository layers to controller methods. `CrudAnalyzer` uses these operations as its primary detection source, falling back to existing HTTP-method/keyword detection.

**Tech Stack:** Python 3.11+, dataclasses, Claude Code CLI / Anthropic API (LLM)

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `knowledge/laravel.md` | Modify | Add CRUD method patterns + call hierarchy for Laravel/Eloquent |
| `knowledge/rails.md` | Modify | Add CRUD method patterns + call hierarchy for Rails/ActiveRecord |
| `knowledge/django.md` | Modify | Add CRUD method patterns + call hierarchy for Django ORM |
| `knowledge/fastapi.md` | Modify | Add CRUD method patterns + call hierarchy for SQLAlchemy |
| `knowledge/spring_boot.md` | Modify | Add CRUD method patterns + call hierarchy for JPA/Spring Data |
| `knowledge/express.md` | Modify | Add CRUD method patterns + call hierarchy for Prisma/TypeORM/Sequelize |
| `knowledge/gin.md` | Modify | Add CRUD method patterns + call hierarchy for GORM |
| `knowledge/echo.md` | Modify | Add CRUD method patterns + call hierarchy for GORM/ent |
| `knowledge/actix.md` | Modify | Add CRUD method patterns + call hierarchy for Diesel/SeaORM |
| `knowledge/phoenix.md` | Modify | Add CRUD method patterns + call hierarchy for Ecto |
| `knowledge/nextjs.md` | Modify | Add frontend-specific note (BFF/API Route patterns only) |
| `knowledge/nuxt.md` | Modify | Add frontend-specific note (Nitro server route patterns) |
| `knowledge/flutter.md` | Modify | Add frontend-specific note (API client, no server-side CRUD) |
| `analyzer/source_parser.py` | Modify | Add `EntityOperation` dataclass, `ParsedController.entity_operations` field, new LLM extraction methods |
| `gap/crud_analyzer.py` | Modify | Add `_check_entity_operations`, change detection priority, full evidence collection |
| `main.py` | Modify | Pass `entity_operations` to `CrudAnalyzer`, serialize/deserialize in checkpoint |
| `tests/test_entity_operation_parsing.py` | Create | Unit tests for EntityOperation JSON parsing |
| `tests/test_crud_analyzer_entity_ops.py` | Create | Unit tests for CrudAnalyzer with EntityOperation |
| `tests/test_attach_operations.py` | Create | Unit tests for _attach_operations_to_controllers |

---

### Task 1: Add EntityOperation dataclass and ParsedController field

**Files:**
- Modify: `analyzer/source_parser.py:9` (imports), `analyzer/source_parser.py:38-47` (after ParsedController), `analyzer/source_parser.py:49-57` (ParsedModel)

- [ ] **Step 1: Add EntityOperation dataclass after the existing dataclass imports**

In `analyzer/source_parser.py`, add the new dataclass after `ParsedPage` (after line 71):

```python
@dataclass
class EntityOperation:
    """エンティティに対するCRUD操作の検出結果"""
    entity_class: str          # 操作対象のエンティティクラス名 (例: "Stock")
    operation: str             # "Create" | "Read" | "Update" | "Delete"
    method_signature: str      # 検出されたメソッド/パターン (例: "Stock::where(...)->decrement('qty')")
    source_file: str           # 操作が記述されたファイルパス
    source_class: str          # 操作が記述されたクラス名 (例: "OrderService")
    source_method: str         # 操作が記述されたメソッド名 (例: "createOrder")
    call_chain: list[str] = field(default_factory=list)  # コール階層
```

- [ ] **Step 2: Add entity_operations field to ParsedController**

In `analyzer/source_parser.py`, add a new field to the `ParsedController` dataclass (after line 47, the `request_rules` field):

```python
    entity_operations: dict[str, list] = field(default_factory=dict)
    # メソッド名 → そのメソッドから到達するEntityOperationリスト
```

Note: The type hint uses `list` instead of `list[EntityOperation]` to avoid forward reference issues since `EntityOperation` is defined after `ParsedController`. The actual values will be `EntityOperation` instances.

- [ ] **Step 3: Verify the module still imports cleanly**

Run: `cd /Users/go/work/github/rdra-analyzer && python -c "from analyzer.source_parser import EntityOperation, ParsedController, ParsedRoute, ParsedModel, ParsedPage; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add analyzer/source_parser.py
git commit -m "feat: add EntityOperation dataclass and ParsedController.entity_operations field"
```

---

### Task 2: Add EntityOperation JSON parsing and attach helper

**Files:**
- Modify: `analyzer/source_parser.py` (add methods to SourceParser class)
- Create: `tests/test_entity_operation_parsing.py`

- [ ] **Step 1: Write failing test for EntityOperation JSON parsing**

Create `tests/test_entity_operation_parsing.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/go/work/github/rdra-analyzer && python -m pytest tests/test_entity_operation_parsing.py -v`
Expected: FAIL — `_parse_entity_operations_json` does not exist yet

- [ ] **Step 3: Implement `_parse_entity_operations_json` in SourceParser**

In `analyzer/source_parser.py`, add this method to the `SourceParser` class (after `_parse_pages_json` around line 494):

```python
    def _parse_entity_operations_json(self, text: str) -> list[EntityOperation]:
        """JSON テキストを EntityOperation リストに変換する"""
        try:
            data = self._extract_json(text)
        except (json.JSONDecodeError, ValueError):
            return []

        operations: list[EntityOperation] = []
        for item in data.get("entity_operations", []):
            operations.append(EntityOperation(
                entity_class=item.get("entity_class", ""),
                operation=item.get("operation", ""),
                method_signature=item.get("method_signature", ""),
                source_file=item.get("source_file", ""),
                source_class=item.get("source_class", ""),
                source_method=item.get("source_method", ""),
                call_chain=item.get("call_chain", []),
            ))
        return operations
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/go/work/github/rdra-analyzer && python -m pytest tests/test_entity_operation_parsing.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add analyzer/source_parser.py tests/test_entity_operation_parsing.py
git commit -m "feat: add EntityOperation JSON parser with tests"
```

---

### Task 3: Add _attach_operations_to_controllers helper

**Files:**
- Modify: `analyzer/source_parser.py`
- Create: `tests/test_attach_operations.py`

- [ ] **Step 1: Write failing test for _attach_operations_to_controllers**

Create `tests/test_attach_operations.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/go/work/github/rdra-analyzer && python -m pytest tests/test_attach_operations.py -v`
Expected: FAIL — `_attach_operations_to_controllers` does not exist yet

- [ ] **Step 3: Implement `_attach_operations_to_controllers`**

In `analyzer/source_parser.py`, add this method to the `SourceParser` class (after `_parse_entity_operations_json`):

```python
    def _attach_operations_to_controllers(
        self,
        controllers: list[ParsedController],
        operations: list[EntityOperation],
    ) -> None:
        """EntityOperationのcall_chainからコントローラーメソッドを特定し紐付ける"""
        # コントローラー名→オブジェクトの索引を構築
        ctrl_index: dict[str, ParsedController] = {}
        for ctrl in controllers:
            ctrl_index[ctrl.class_name] = ctrl

        for op in operations:
            if not op.call_chain:
                continue

            # call_chain の先頭要素からコントローラー名.メソッド名を抽出
            # 例: "OrderController.store" → ("OrderController", "store")
            first = op.call_chain[0]
            if "." not in first:
                continue

            ctrl_name, method_name = first.rsplit(".", 1)
            ctrl = ctrl_index.get(ctrl_name)
            if ctrl is None:
                continue

            if method_name not in ctrl.entity_operations:
                ctrl.entity_operations[method_name] = []
            ctrl.entity_operations[method_name].append(op)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/go/work/github/rdra-analyzer && python -m pytest tests/test_attach_operations.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add analyzer/source_parser.py tests/test_attach_operations.py
git commit -m "feat: add _attach_operations_to_controllers helper with tests"
```

---

### Task 4: Add LLM extraction methods for entity operations

**Files:**
- Modify: `analyzer/source_parser.py` (add `_extract_entity_operations_with_llm`, `_extract_entity_operations_batch`, `_extract_entity_operations_with_api`)

- [ ] **Step 1: Add ENTITY_BATCH_SIZE constant**

In `analyzer/source_parser.py`, add after the existing imports (around line 12):

```python
ENTITY_BATCH_SIZE = 20
```

- [ ] **Step 2: Add `_extract_entity_operations_with_llm` method with batch splitting**

In `analyzer/source_parser.py`, add to the `SourceParser` class after `_extract_pages_with_llm` (around line 350):

```python
    def _extract_entity_operations_with_llm(
        self, repo_path: Path, context_text: str, models: list[ParsedModel]
    ) -> list[EntityOperation]:
        """エンティティモデルからCRUD操作を検出し、コントローラーまで遡って追跡する"""
        if not models:
            return []

        if len(models) <= ENTITY_BATCH_SIZE:
            return self._extract_entity_operations_batch(repo_path, context_text, models)

        all_operations: list[EntityOperation] = []
        for i in range(0, len(models), ENTITY_BATCH_SIZE):
            batch = models[i:i + ENTITY_BATCH_SIZE]
            operations = self._extract_entity_operations_batch(repo_path, context_text, batch)
            all_operations.extend(operations)
        return all_operations

    def _extract_entity_operations_batch(
        self, repo_path: Path, context_text: str, models: list[ParsedModel]
    ) -> list[EntityOperation]:
        """エンティティ操作をバッチ単位でLLM抽出する"""
        entity_list = "\n".join(
            f"- {m.class_name} (table: {m.table_name})" for m in models
        )

        prompt = f"""{context_text}

## 対象エンティティ
{entity_list}

## 指示

上記のエンティティに対するCRUD操作を、ソースコードから検出してください。

### 優先順位
1. CLAUDE.md / AGENTS.md に記載されたアーキテクチャ・規約（最優先）
2. プロジェクトの実際のソースコード
3. フレームワーク知識（上記が不明確な場合のフォールバック）

### 手順
1. 各エンティティのモデル/エンティティクラスのソースコードを確認する
2. そのエンティティに対してCreate/Read/Update/Deleteを行っているコードを
   プロジェクト全体から探す（Controller, Service, Repository, Job, EventListener等）
3. 各操作について、呼び出し元をControllerメソッドまで遡って追跡する
4. 1つのControllerメソッドが複数エンティティを操作している場合、すべて記録する

### 注意
- HTTPメソッドではなく、実際のコード上のCRUD操作で判断すること
- 間接的な操作も検出すること
  例: OrderController.store() → OrderService.createOrder() → Stock::decrement()
  この場合 Stock に対する Update 操作として記録
- Cascade削除やイベントリスナー経由の操作も可能な範囲で検出する

以下のJSON形式のみを返してください（説明不要）:
{{{{
  "entity_operations": [
    {{{{
      "entity_class": "Stock",
      "operation": "Update",
      "method_signature": "Stock::where(...)->decrement('qty')",
      "source_file": "app/Services/OrderService.php",
      "source_class": "OrderService",
      "source_method": "createOrder",
      "call_chain": ["OrderController.store", "OrderService.createOrder"]
    }}}}
  ]
}}}}"""

        try:
            result_text = self._llm.analyze_codebase(
                path=str(repo_path),
                prompt=prompt,
                timeout=self._config.CLAUDE_ANALYZE_TIMEOUT,
            )
            return self._parse_entity_operations_json(result_text)
        except Exception as e:
            import sys
            print(f"  [warn] エンティティ操作抽出に失敗: {e}", file=sys.stderr)
            return []
```

- [ ] **Step 3: Add `_extract_entity_operations_with_api` fallback method**

In `analyzer/source_parser.py`, add to the `SourceParser` class after `_extract_models_with_api` (around line 402):

```python
    def _extract_entity_operations_with_api(
        self, context_text: str, models: list[ParsedModel], controllers: list[ParsedController]
    ) -> list[EntityOperation]:
        """プロジェクトコンテキストからLLMでエンティティ操作を推定する"""
        entity_list = "\n".join(
            f"- {m.class_name} (table: {m.table_name})" for m in models
        )
        controller_list = "\n".join(
            f"- {c.class_name}: {', '.join(c.methods)}" for c in controllers
        )

        system_prompt = "あなたはソフトウェアアーキテクチャの専門家です。プロジェクト情報からエンティティのCRUD操作を推定してください。"
        user_message = f"""{context_text}

## 対象エンティティ
{entity_list}

## コントローラー一覧
{controller_list}

上記の情報から、各エンティティに対するCRUD操作とその呼び出し元を推定してください。
CLAUDE.md / AGENTS.md の規約を最優先し、次にフレームワーク知識で推定してください。

以下のJSON形式のみで返してください:
{{
  "entity_operations": [
    {{"entity_class": "User", "operation": "Create", "method_signature": "", "source_file": "", "source_class": "UserController", "source_method": "store", "call_chain": ["UserController.store"]}}
  ]
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=system_prompt,
            )
            return self._parse_entity_operations_json(response)
        except Exception:
            return []
```

- [ ] **Step 4: Verify the module still imports cleanly**

Run: `cd /Users/go/work/github/rdra-analyzer && python -c "from analyzer.source_parser import SourceParser; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add analyzer/source_parser.py
git commit -m "feat: add LLM extraction methods for entity operations with batch splitting"
```

---

### Task 5: Integrate entity operations into parse_repo pipeline

**Files:**
- Modify: `analyzer/source_parser.py:85-130` (`parse_repo` method)

- [ ] **Step 1: Update parse_repo to call entity operations extraction and attach to controllers**

In `analyzer/source_parser.py`, modify the `parse_repo` method. Replace the current body (lines 101-130):

```python
    def parse_repo(self, repo_path: Path) -> dict:
        """
        リポジトリを解析してルート・ハンドラー・モデル・ビューを抽出する。

        Args:
            repo_path: 解析対象リポジトリのパス

        Returns:
            dict: {
                "routes": [ParsedRoute],
                "controllers": [ParsedController],
                "models": [ParsedModel],
                "pages": [ParsedPage],
                "entity_operations": [EntityOperation],
                "project_context": ProjectContext,
            }
        """
        # プロジェクトコンテキストを構築
        ctx = build_context(repo_path)
        context_text = format_context_for_prompt([ctx])

        entity_operations: list[EntityOperation] = []

        if self._llm is not None and hasattr(self._llm, "analyze_codebase"):
            # LLM 駆動の解析
            routes = self._extract_routes_with_llm(repo_path, context_text)
            controllers = self._extract_controllers_with_llm(repo_path, context_text)
            models = self._extract_models_with_llm(repo_path, context_text)
            pages = self._extract_pages_with_llm(repo_path, context_text)
            # エンティティ操作の抽出（models の後に実行）
            entity_operations = self._extract_entity_operations_with_llm(
                repo_path, context_text, models
            )
            self._attach_operations_to_controllers(controllers, entity_operations)
        elif self._llm is not None:
            # Anthropic API のみ（analyze_codebase なし）→ コンテキストベースで推定
            routes = self._extract_routes_with_api(context_text)
            controllers = []
            models = self._extract_models_with_api(context_text)
            pages = []
            entity_operations = self._extract_entity_operations_with_api(
                context_text, models, controllers
            )
        else:
            # LLM なし → マニフェスト＋ディレクトリ構造からの最低限の推定
            routes = []
            controllers = []
            models = []
            pages = []

        return {
            "routes": routes,
            "controllers": controllers,
            "models": models,
            "pages": pages,
            "entity_operations": entity_operations,
            "project_context": ctx,
        }
```

- [ ] **Step 2: Update parse_all_repos to aggregate entity_operations**

In `analyzer/source_parser.py`, modify `parse_all_repos` (around line 132):

```python
    def parse_all_repos(self) -> dict:
        """
        設定されたすべてのリポジトリを解析して統合する。

        Returns:
            dict: 統合された解析結果
        """
        all_routes: list[ParsedRoute] = []
        all_controllers: list[ParsedController] = []
        all_models: list[ParsedModel] = []
        all_pages: list[ParsedPage] = []
        all_entity_operations: list[EntityOperation] = []
        all_contexts: list[ProjectContext] = []

        for repo_path in self._config.repo_paths:
            result = self.parse_repo(repo_path)
            all_routes.extend(result["routes"])
            all_controllers.extend(result["controllers"])
            all_models.extend(result["models"])
            all_pages.extend(result["pages"])
            all_entity_operations.extend(result.get("entity_operations", []))
            all_contexts.append(result["project_context"])

        return {
            "routes": all_routes,
            "controllers": all_controllers,
            "models": all_models,
            "pages": all_pages,
            "entity_operations": all_entity_operations,
            "project_contexts": all_contexts,
        }
```

- [ ] **Step 3: Verify the module still imports cleanly**

Run: `cd /Users/go/work/github/rdra-analyzer && python -c "from analyzer.source_parser import SourceParser; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add analyzer/source_parser.py
git commit -m "feat: integrate entity operations extraction into parse_repo pipeline"
```

---

### Task 6: Update CrudAnalyzer with entity operations support

**Files:**
- Modify: `gap/crud_analyzer.py`
- Create: `tests/test_crud_analyzer_entity_ops.py`

- [ ] **Step 1: Write failing tests for _check_entity_operations**

Create `tests/test_crud_analyzer_entity_ops.py`:

```python
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
    # Create以外は不足 → 3つのギャップ
    assert len(gaps) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/go/work/github/rdra-analyzer && python -m pytest tests/test_crud_analyzer_entity_ops.py -v`
Expected: FAIL — `_check_entity_operations` does not exist, `analyze` signature mismatch

- [ ] **Step 3: Add import and `_check_entity_operations` method to CrudAnalyzer**

In `gap/crud_analyzer.py`, add import at line 17 (after existing imports):

```python
from analyzer.source_parser import EntityOperation
```

Add new method to `CrudAnalyzer` class (after `_check_usecases`, around line 292):

```python
    def _check_entity_operations(
        self,
        status: EntityCrudStatus,
        entity: Entity,
        entity_operations: list[EntityOperation],
    ) -> None:
        """EntityOperationからエンティティのCRUD操作を検出する（全証跡収集）"""
        for op in entity_operations:
            if op.entity_class.lower() != entity.class_name.lower():
                continue

            chain_str = " → ".join(op.call_chain) if op.call_chain else op.source_class
            evidence = f"{chain_str}: {op.method_signature}"

            if op.operation == "Create":
                status.has_create = True
                status.create_evidence.append(evidence)
            elif op.operation == "Read":
                status.has_read = True
                status.read_evidence.append(evidence)
            elif op.operation == "Update":
                status.has_update = True
                status.update_evidence.append(evidence)
            elif op.operation == "Delete":
                status.has_delete = True
                status.delete_evidence.append(evidence)
```

- [ ] **Step 4: Update `analyze` and `_analyze_entity` signatures**

In `gap/crud_analyzer.py`, modify `analyze` method (around line 112):

```python
    def analyze(
        self,
        entities: list[Entity],
        routes: list[ParsedRoute],
        scenarios: list[OperationScenario],
        usecases: list[Usecase],
        entity_operations: list[EntityOperation] = None,
    ) -> tuple[list[EntityCrudStatus], list[CrudGap]]:
```

Update the loop inside `analyze` (around line 134):

```python
        for entity in entities:
            status = self._analyze_entity(entity, routes, scenarios, usecases, entity_operations)
            statuses.append(status)
```

Modify `_analyze_entity` (around line 143):

```python
    def _analyze_entity(
        self,
        entity: Entity,
        routes: list[ParsedRoute],
        scenarios: list[OperationScenario],
        usecases: list[Usecase],
        entity_operations: list[EntityOperation] = None,
    ) -> EntityCrudStatus:
        """1エンティティのCRUDステータスを分析する"""
        status = EntityCrudStatus(
            entity_name=entity.name,
            class_name=entity.class_name,
        )

        # 1. EntityOperation からCRUD操作を検出（最優先）
        if entity_operations:
            self._check_entity_operations(status, entity, entity_operations)

        # 2. 操作シナリオからCRUD操作を検出（フォールバック）
        self._check_scenarios(status, entity, scenarios)

        # 3. ルートからCRUD操作を検出（フォールバック）
        self._check_routes(status, entity, routes)

        # 4. ユースケースからCRUD操作を検出（フォールバック）
        self._check_usecases(status, entity, usecases)

        return status
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/go/work/github/rdra-analyzer && python -m pytest tests/test_crud_analyzer_entity_ops.py -v`
Expected: All 6 tests PASS

- [ ] **Step 6: Commit**

```bash
git add gap/crud_analyzer.py tests/test_crud_analyzer_entity_ops.py
git commit -m "feat: add entity operations support to CrudAnalyzer with full evidence collection"
```

---

### Task 7: Update main.py checkpoint and gap command

**Files:**
- Modify: `main.py:125-176` (checkpoint functions), `main.py:957-1043` (run_gap)

- [ ] **Step 1: Add EntityOperation serialization to checkpoint**

In `main.py`, add a helper function after `_page_to_dict` (around line 144):

```python
    def _entity_operation_to_dict(op) -> dict:
        return {"entity_class": op.entity_class, "operation": op.operation,
                "method_signature": op.method_signature, "source_file": op.source_file,
                "source_class": op.source_class, "source_method": op.source_method,
                "call_chain": op.call_chain}
```

In the `serializable` dict (around line 146), add:

```python
    serializable = {
        "routes": [_route_to_dict(r) for r in data.get("routes", [])],
        "controllers": [_controller_to_dict(c) for c in data.get("controllers", [])],
        "models": [_model_to_dict(m) for m in data.get("models", [])],
        "pages": [_page_to_dict(p) for p in data.get("pages", [])],
        "entity_operations": [_entity_operation_to_dict(op) for op in data.get("entity_operations", [])],
        "completed_repos": data.get("completed_repos", []),
        "phase": data.get("phase", "parse"),
    }
```

- [ ] **Step 2: Add EntityOperation deserialization to _load_parse_checkpoint**

In `main.py`, modify `_load_parse_checkpoint` (around line 158). Add import and deserialization:

```python
def _load_parse_checkpoint(checkpoint_path: Path) -> dict | None:
    """ソースコード解析の中間結果を読み込む"""
    if not checkpoint_path.exists():
        return None
    from analyzer.source_parser import ParsedRoute, ParsedController, ParsedModel, ParsedPage, EntityOperation

    data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    routes = [ParsedRoute(**r) for r in data.get("routes", [])]
    controllers = [ParsedController(**c) for c in data.get("controllers", [])]
    models = [ParsedModel(**m) for m in data.get("models", [])]
    pages = [ParsedPage(**p) for p in data.get("pages", [])]
    entity_operations = [EntityOperation(**op) for op in data.get("entity_operations", [])]
    return {
        "routes": routes,
        "controllers": controllers,
        "models": models,
        "pages": pages,
        "entity_operations": entity_operations,
        "completed_repos": data.get("completed_repos", []),
        "phase": data.get("phase", "parse"),
    }
```

- [ ] **Step 3: Update run_gap to load and pass entity_operations**

In `main.py`, modify `run_gap` function (around line 1011-1032). After loading routes and models from checkpoint, add entity_operations loading:

```python
    from analyzer.source_parser import ParsedRoute, ParsedModel, EntityOperation
    routes = [ParsedRoute(**r) if isinstance(r, dict) else r for r in cp["routes"]]
    models = [ParsedModel(**m) if isinstance(m, dict) else m for m in cp["models"]]
    entity_operations = [
        EntityOperation(**op) if isinstance(op, dict) else op
        for op in cp.get("entity_operations", [])
    ]
    console.print(f"  チェックポイントから読み込み: ルート {len(routes)}件 | モデル {len(models)}件 | エンティティ操作 {len(entity_operations)}件")
```

Then update the `analyzer.analyze()` call (around line 1032):

```python
    statuses, gaps = analyzer.analyze(entities, routes, scenarios, usecases, entity_operations)
```

- [ ] **Step 4: Verify the module still imports cleanly**

Run: `cd /Users/go/work/github/rdra-analyzer && python -c "import main; print('OK')"`
Expected: `OK` (or may require env vars — just check no syntax errors with `python -c "import ast; ast.parse(open('main.py').read()); print('OK')")`)

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: add entity_operations to checkpoint serialization and gap command"
```

---

### Task 8: Add CRUD patterns and call hierarchy to backend knowledge files (Part 1: PHP/Ruby/Python)

**Files:**
- Modify: `knowledge/laravel.md`
- Modify: `knowledge/rails.md`
- Modify: `knowledge/django.md`
- Modify: `knowledge/fastapi.md`

- [ ] **Step 1: Add CRUD patterns and call hierarchy to laravel.md**

Append to `knowledge/laravel.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### Eloquent Model 直接操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `Model::create([...])`, `new Model(); $model->save()`, `Model::insert([...])`, `Model::firstOrCreate([...])`, `Model::updateOrCreate([...])` |
| Read | `Model::find($id)`, `Model::where(...)->get()`, `Model::all()`, `Model::first()`, `Model::paginate()`, `Model::findOrFail($id)` |
| Update | `$model->update([...])`, `$model->save()` (既存レコード), `Model::where(...)->update([...])`, `$model->increment(...)`, `$model->decrement(...)` |
| Delete | `$model->delete()`, `Model::destroy($id)`, `Model::where(...)->delete()`, `$model->forceDelete()`, `$model->trash()` |

### Query Builder 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `DB::table('x')->insert([...])` |
| Read | `DB::table('x')->get()`, `DB::table('x')->find($id)`, `DB::table('x')->where(...)->first()` |
| Update | `DB::table('x')->where(...)->update([...])`, `DB::table('x')->increment(...)`, `DB::table('x')->decrement(...)` |
| Delete | `DB::table('x')->where(...)->delete()`, `DB::table('x')->truncate()` |

### リレーション経由の操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `$parent->children()->create([...])`, `$parent->children()->createMany([...])`, `$parent->children()->save($child)` |
| Read | `$parent->children()->get()`, `$parent->children` (動的プロパティ), `$parent->children()->where(...)->get()` |
| Update | `$parent->children()->update([...])` |
| Delete | `$parent->children()->delete()`, `$parent->children()->detach()` (多対多) |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: Controller → Model（直接操作）
- 小〜中規模プロジェクトに多い
- コントローラー内でEloquentモデルを直接操作
```php
public function store(StoreOrderRequest $request) {
    $order = Order::create($request->validated());       // Order: Create
    $order->items()->createMany($request->items);        // OrderItem: Create
    Stock::where('product_id', $pid)->decrement('qty');  // Stock: Update
}
```

### パターン2: Controller → Service → Model
- Service層でビジネスロジックを集約
```php
// Controller
public function store(StoreOrderRequest $request) {
    return $this->orderService->createOrder($request->validated());
}
// Service
public function createOrder(array $data): Order {
    $order = Order::create($data);                       // Order: Create
    $this->stockService->decrementStock($data['items']); // Stock: Update
    Payment::create([...]);                               // Payment: Create
    return $order;
}
```

### パターン3: Controller → Service → Repository → Model
- DDD / クリーンアーキテクチャ
```php
// Repository
class OrderRepository {
    public function create(array $data): Order {
        return Order::create($data);                     // Order: Create
    }
}
// Service
public function createOrder(array $data): Order {
    $order = $this->orderRepo->create($data);
    $this->stockRepo->decrement($data['items']);         // Stock: Update
    return $order;
}
```

### パターン4: Event / Job / Observer 経由
```php
// Observer
class OrderObserver {
    public function created(Order $order) {
        Notification::create([...]);                     // Notification: Create
    }
    public function deleted(Order $order) {
        $order->items()->delete();                       // OrderItem: Delete (cascade)
    }
}
// Job
class ProcessPaymentJob {
    public function handle() {
        Payment::create([...]);                           // Payment: Create
    }
}
```
```

- [ ] **Step 2: Add CRUD patterns and call hierarchy to rails.md**

Append to `knowledge/rails.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### ActiveRecord 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `Model.create(...)`, `Model.new(...).save`, `Model.create!(...)`, `Model.find_or_create_by(...)` |
| Read | `Model.find(id)`, `Model.find_by(...)`, `Model.where(...)`, `Model.all`, `Model.first`, `Model.last`, `Model.pluck(...)` |
| Update | `record.update(...)`, `record.update!(...)`, `record.save`, `Model.update_all(...)`, `record.increment!(...)`, `record.toggle!(...)` |
| Delete | `record.destroy`, `record.destroy!`, `Model.destroy_all(...)`, `record.delete`, `Model.delete_all(...)` |

### リレーション経由の操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `parent.children.create(...)`, `parent.children.build(...)`, `parent.children << child` |
| Read | `parent.children`, `parent.children.where(...)`, `parent.children.find(id)` |
| Update | `parent.children.update_all(...)` |
| Delete | `parent.children.destroy_all`, `parent.children.delete_all` |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: Controller → Model（直接操作）
```ruby
class OrdersController < ApplicationController
  def create
    @order = Order.create!(order_params)               # Order: Create
    @order.order_items.create!(item_params)             # OrderItem: Create
    Stock.where(product_id: pid).decrement!(:qty)       # Stock: Update
  end
end
```

### パターン2: Controller → Service → Model
```ruby
# Controller
def create
  OrderService.new.create_order(order_params)
end
# Service
class OrderService
  def create_order(params)
    order = Order.create!(params)                       # Order: Create
    StockService.new.decrement(params[:items])           # Stock: Update
    order
  end
end
```

### パターン3: Callback / Job 経由
```ruby
class Order < ApplicationRecord
  after_create :send_notification
  after_destroy :restore_stock
  private
  def send_notification
    Notification.create!(...)                            # Notification: Create
  end
  def restore_stock
    stock_items.each { |s| s.increment!(:qty) }         # Stock: Update
  end
end
```
```

- [ ] **Step 3: Add CRUD patterns and call hierarchy to django.md**

Append to `knowledge/django.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### Django ORM 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `Model.objects.create(...)`, `Model(...).save()`, `Model.objects.get_or_create(...)`, `Model.objects.bulk_create([...])` |
| Read | `Model.objects.get(pk=id)`, `Model.objects.filter(...)`, `Model.objects.all()`, `Model.objects.first()`, `Model.objects.values(...)` |
| Update | `obj.save()` (既存), `Model.objects.filter(...).update(...)`, `obj.field = value; obj.save()`, `Model.objects.bulk_update([...])` |
| Delete | `obj.delete()`, `Model.objects.filter(...).delete()` |

### リレーション経由の操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `parent.children.create(...)`, `parent.children.add(child)` |
| Read | `parent.children.all()`, `parent.children.filter(...)` |
| Update | `parent.children.update(...)` |
| Delete | `parent.children.remove(child)`, `parent.children.clear()` |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: View → Model（直接操作）
- Function-based views や ModelViewSet でよく見られる
```python
class OrderViewSet(viewsets.ModelViewSet):
    def perform_create(self, serializer):
        order = serializer.save()                        # Order: Create
        Stock.objects.filter(product=pid).update(qty=F('qty') - 1)  # Stock: Update
```

### パターン2: View → Service → Model
```python
# views.py
class OrderCreateView(APIView):
    def post(self, request):
        return OrderService().create_order(request.data)
# services.py
class OrderService:
    def create_order(self, data):
        order = Order.objects.create(**data)              # Order: Create
        StockService().decrement(data['items'])           # Stock: Update
        Payment.objects.create(order=order, ...)          # Payment: Create
        return order
```

### パターン3: Signal 経由
```python
@receiver(post_save, sender=Order)
def on_order_created(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(...)                  # Notification: Create
@receiver(post_delete, sender=Order)
def on_order_deleted(sender, instance, **kwargs):
    instance.items.all().delete()                         # OrderItem: Delete
```
```

- [ ] **Step 4: Add CRUD patterns and call hierarchy to fastapi.md**

Append to `knowledge/fastapi.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### SQLAlchemy 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `db.add(Model(...))`, `db.add_all([...])`, `db.commit()` (add後) |
| Read | `db.query(Model).get(id)`, `db.query(Model).filter(...).all()`, `db.query(Model).first()`, `db.execute(select(Model))` |
| Update | `obj.field = value; db.commit()`, `db.query(Model).filter(...).update({...})`, `db.execute(update(Model).where(...))` |
| Delete | `db.delete(obj); db.commit()`, `db.query(Model).filter(...).delete()`, `db.execute(delete(Model).where(...))` |

### Tortoise ORM 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `await Model.create(...)`, `await Model.bulk_create([...])` |
| Read | `await Model.get(id=...)`, `await Model.filter(...)`, `await Model.all()` |
| Update | `obj.field = value; await obj.save()`, `await Model.filter(...).update(...)` |
| Delete | `await obj.delete()`, `await Model.filter(...).delete()` |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: Router → CRUD module → Model
- FastAPI 公式テンプレートのパターン
```python
# routers/order.py
@router.post("/orders")
async def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    return crud.order.create(db, order)
# crud/order.py
def create(db: Session, order: OrderCreate) -> Order:
    db_order = Order(**order.dict())
    db.add(db_order)                                     # Order: Create
    db.commit()
    stock = db.query(Stock).filter(...).first()
    stock.qty -= order.qty                               # Stock: Update
    db.commit()
    return db_order
```

### パターン2: Router → Service → Repository → Model
```python
# service
class OrderService:
    def __init__(self, order_repo: OrderRepository, stock_repo: StockRepository):
        self.order_repo = order_repo
        self.stock_repo = stock_repo
    async def create_order(self, data: OrderCreate) -> Order:
        order = await self.order_repo.create(data)       # Order: Create
        await self.stock_repo.decrement(data.product_id) # Stock: Update
        return order
```
```

- [ ] **Step 5: Commit**

```bash
git add knowledge/laravel.md knowledge/rails.md knowledge/django.md knowledge/fastapi.md
git commit -m "feat: add CRUD patterns and call hierarchy to PHP/Ruby/Python knowledge files"
```

---

### Task 9: Add CRUD patterns and call hierarchy to backend knowledge files (Part 2: Java/JS/Go/Rust/Elixir)

**Files:**
- Modify: `knowledge/spring_boot.md`
- Modify: `knowledge/express.md`
- Modify: `knowledge/gin.md`
- Modify: `knowledge/echo.md`
- Modify: `knowledge/actix.md`
- Modify: `knowledge/phoenix.md`

- [ ] **Step 1: Add CRUD patterns and call hierarchy to spring_boot.md**

Append to `knowledge/spring_boot.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### JPA Repository (Spring Data)
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `repository.save(new Entity(...))`, `repository.saveAll(list)`, `repository.saveAndFlush(entity)` |
| Read | `repository.findById(id)`, `repository.findAll()`, `repository.findBy*()`, `repository.existsById(id)`, `repository.count()` |
| Update | `repository.save(existingEntity)` (IDあり), `@Modifying @Query("UPDATE ...")` |
| Delete | `repository.delete(entity)`, `repository.deleteById(id)`, `repository.deleteAll(...)`, `repository.deleteAllInBatch()` |

### EntityManager 直接操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `em.persist(entity)` |
| Read | `em.find(Entity.class, id)`, `em.createQuery(...)`, `em.createNamedQuery(...)` |
| Update | `em.merge(entity)` |
| Delete | `em.remove(entity)` |

### JdbcTemplate / NamedParameterJdbcTemplate
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `jdbcTemplate.update("INSERT INTO ...")` |
| Read | `jdbcTemplate.query(...)`, `jdbcTemplate.queryForObject(...)` |
| Update | `jdbcTemplate.update("UPDATE ...")` |
| Delete | `jdbcTemplate.update("DELETE FROM ...")` |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: Controller → Service → Repository（標準）
```java
// Controller
@PostMapping
public OrderDto createOrder(@RequestBody @Valid OrderCreateDto dto) {
    return orderService.createOrder(dto);
}
// Service
@Transactional
public OrderDto createOrder(OrderCreateDto dto) {
    Order order = orderRepository.save(new Order(...));     // Order: Create
    stockRepository.decrementByProductId(dto.productId());  // Stock: Update
    paymentRepository.save(new Payment(...));                // Payment: Create
    return OrderDto.from(order);
}
```

### パターン2: EventListener / ApplicationEvent 経由
```java
@TransactionalEventListener
public void onOrderCreated(OrderCreatedEvent event) {
    notificationRepository.save(new Notification(...));     // Notification: Create
}

@EventListener
public void onOrderDeleted(OrderDeletedEvent event) {
    orderItemRepository.deleteAllByOrderId(event.orderId()); // OrderItem: Delete
}
```

### パターン3: @Scheduled / Async 経由
```java
@Scheduled(cron = "0 0 * * * *")
public void cleanupExpiredOrders() {
    orderRepository.deleteAllByStatusAndCreatedBefore(...);  // Order: Delete
}
```
```

- [ ] **Step 2: Add CRUD patterns and call hierarchy to express.md**

Append to `knowledge/express.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### Prisma 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `prisma.model.create({ data: ... })`, `prisma.model.createMany({ data: [...] })` |
| Read | `prisma.model.findUnique({ where: ... })`, `prisma.model.findMany(...)`, `prisma.model.findFirst(...)`, `prisma.model.count(...)` |
| Update | `prisma.model.update({ where: ..., data: ... })`, `prisma.model.updateMany(...)`, `prisma.model.upsert(...)` |
| Delete | `prisma.model.delete({ where: ... })`, `prisma.model.deleteMany(...)` |

### TypeORM 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `repository.save(new Entity())`, `repository.create(...)`, `repository.insert(...)` |
| Read | `repository.findOne(...)`, `repository.find(...)`, `repository.findOneBy(...)`, `repository.createQueryBuilder(...)` |
| Update | `repository.save(existing)`, `repository.update(id, ...)` |
| Delete | `repository.delete(id)`, `repository.remove(entity)`, `repository.softDelete(id)` |

### Sequelize 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `Model.create(...)`, `Model.bulkCreate([...])` |
| Read | `Model.findByPk(id)`, `Model.findAll(...)`, `Model.findOne(...)`, `Model.count(...)` |
| Update | `instance.update(...)`, `instance.save()`, `Model.update(..., { where: ... })` |
| Delete | `instance.destroy()`, `Model.destroy({ where: ... })` |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: Controller → Model（直接操作）
```typescript
// controller
export const createOrder = async (req: Request, res: Response) => {
    const order = await prisma.order.create({ data: req.body });   // Order: Create
    await prisma.stock.update({ where: { id: pid }, data: { qty: { decrement: 1 } } }); // Stock: Update
    res.json(order);
};
```

### パターン2: Controller → Service → Model
```typescript
// controller
export const createOrder = async (req: Request, res: Response) => {
    const order = await orderService.createOrder(req.body);
    res.json(order);
};
// service
export class OrderService {
    async createOrder(data: OrderInput) {
        const order = await prisma.order.create({ data });         // Order: Create
        await this.stockService.decrement(data.productId);         // Stock: Update
        await prisma.payment.create({ data: { orderId: order.id } }); // Payment: Create
        return order;
    }
}
```
```

- [ ] **Step 3: Add CRUD patterns and call hierarchy to gin.md**

Append to `knowledge/gin.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### GORM 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `db.Create(&model)`, `db.CreateInBatches(&models, batchSize)` |
| Read | `db.First(&model, id)`, `db.Find(&models)`, `db.Where(...).Find(&models)`, `db.Take(&model)` |
| Update | `db.Save(&model)`, `db.Model(&model).Update(...)`, `db.Model(&model).Updates(...)`, `db.Where(...).Update(...)` |
| Delete | `db.Delete(&model, id)`, `db.Where(...).Delete(&Model{})`, `db.Unscoped().Delete(&model)` (hard delete) |

### database/sql 直接操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `db.Exec("INSERT INTO ...")`, `db.ExecContext(ctx, "INSERT INTO ...")` |
| Read | `db.Query("SELECT ...")`, `db.QueryRow("SELECT ...")`, `db.QueryContext(...)` |
| Update | `db.Exec("UPDATE ...")` |
| Delete | `db.Exec("DELETE FROM ...")` |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: Handler → Service → Repository
```go
// handler
func (h *OrderHandler) CreateOrder(c *gin.Context) {
    order, err := h.service.CreateOrder(c.Request.Context(), &input)
    // ...
}
// service
func (s *OrderService) CreateOrder(ctx context.Context, input *OrderInput) (*Order, error) {
    order, err := s.orderRepo.Create(ctx, input)            // Order: Create
    err = s.stockRepo.Decrement(ctx, input.ProductID, qty)  // Stock: Update
    return order, err
}
// repository
func (r *OrderRepository) Create(ctx context.Context, input *OrderInput) (*Order, error) {
    order := &Order{...}
    return order, r.db.WithContext(ctx).Create(order).Error  // Order: Create
}
```

### パターン2: Handler → Model（直接操作、小規模）
```go
func CreateOrder(c *gin.Context) {
    var order Order
    db.Create(&order)                                        // Order: Create
    db.Model(&Stock{}).Where("product_id = ?", pid).
        Update("qty", gorm.Expr("qty - ?", 1))              // Stock: Update
}
```
```

- [ ] **Step 4: Add CRUD patterns and call hierarchy to echo.md**

Append to `knowledge/echo.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### GORM 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `db.Create(&model)`, `db.CreateInBatches(&models, batchSize)` |
| Read | `db.First(&model, id)`, `db.Find(&models)`, `db.Where(...).Find(&models)`, `db.Take(&model)` |
| Update | `db.Save(&model)`, `db.Model(&model).Update(...)`, `db.Model(&model).Updates(...)` |
| Delete | `db.Delete(&model, id)`, `db.Where(...).Delete(&Model{})` |

### ent 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `client.User.Create().Set*(...).Save(ctx)` |
| Read | `client.User.Get(ctx, id)`, `client.User.Query().Where(...).All(ctx)` |
| Update | `client.User.UpdateOneID(id).Set*(...).Save(ctx)`, `client.User.Update().Where(...).Save(ctx)` |
| Delete | `client.User.DeleteOneID(id).Exec(ctx)`, `client.User.Delete().Where(...).Exec(ctx)` |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: Handler → Service → Repository
- Gin と同一パターン（Go の標準的なレイヤリング）
```go
func (h *OrderHandler) CreateOrder(c echo.Context) error {
    order, err := h.service.CreateOrder(c.Request().Context(), &input)
    // ...
}
```
コール階層の詳細は gin.md のパターンを参照。
```

- [ ] **Step 5: Add CRUD patterns and call hierarchy to actix.md**

Append to `knowledge/actix.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### Diesel 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `diesel::insert_into(table).values(&new_record).execute(&mut conn)`, `diesel::insert_into(table).values(&new_record).get_result(&mut conn)` |
| Read | `table.find(id).first(&mut conn)`, `table.filter(...).load(&mut conn)`, `table.select(...).load(&mut conn)` |
| Update | `diesel::update(table.find(id)).set(...).execute(&mut conn)`, `diesel::update(table.filter(...)).set(...)` |
| Delete | `diesel::delete(table.find(id)).execute(&mut conn)`, `diesel::delete(table.filter(...)).execute(&mut conn)` |

### SeaORM 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `Entity::insert(active_model).exec(&db).await`, `Entity::insert_many([...]).exec(&db).await` |
| Read | `Entity::find_by_id(id).one(&db).await`, `Entity::find().filter(...).all(&db).await` |
| Update | `active_model.update(&db).await`, `Entity::update_many().set(...).filter(...).exec(&db).await` |
| Delete | `active_model.delete(&db).await`, `Entity::delete_by_id(id).exec(&db).await` |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: Handler → Service → Repository
```rust
// handler
async fn create_order(data: web::Json<OrderInput>, svc: web::Data<OrderService>) -> impl Responder {
    let order = svc.create_order(data.into_inner()).await?;
    HttpResponse::Created().json(order)
}
// service
impl OrderService {
    async fn create_order(&self, input: OrderInput) -> Result<Order> {
        let order = self.order_repo.create(&input).await?;   // Order: Create
        self.stock_repo.decrement(input.product_id).await?;  // Stock: Update
        Ok(order)
    }
}
```
```

- [ ] **Step 6: Add CRUD patterns and call hierarchy to phoenix.md**

Append to `knowledge/phoenix.md`:

```markdown

## CRUD操作パターン

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。

### Ecto 操作
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `Repo.insert(changeset)`, `Repo.insert!(changeset)`, `Repo.insert_all(table, [...])` |
| Read | `Repo.get(Model, id)`, `Repo.get!(Model, id)`, `Repo.all(Model)`, `Repo.one(query)`, `from(...) \|> Repo.all()` |
| Update | `Repo.update(changeset)`, `Repo.update!(changeset)`, `Repo.update_all(query, set: [...])` |
| Delete | `Repo.delete(record)`, `Repo.delete!(record)`, `Repo.delete_all(query)` |

## コール階層

> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。

### パターン1: Controller → Context → Repo（Phoenix標準）
- Phoenix の Context（ビジネスロジック層）を通じたアクセスが標準
```elixir
# Controller
def create(conn, %{"order" => order_params}) do
  case Orders.create_order(order_params) do
    {:ok, order} -> ...
  end
end
# Context (lib/my_app/orders.ex)
def create_order(attrs) do
  %Order{}
  |> Order.changeset(attrs)
  |> Repo.insert()                                        # Order: Create
  |> case do
    {:ok, order} ->
      Stocks.decrement(order.product_id)                  # Stock: Update
      {:ok, order}
  end
end
```

### パターン2: Ecto.Multi（トランザクション）
```elixir
Ecto.Multi.new()
|> Ecto.Multi.insert(:order, Order.changeset(%Order{}, attrs))   # Order: Create
|> Ecto.Multi.update(:stock, fn %{order: order} ->
     Stock.decrement_changeset(order.product_id)                  # Stock: Update
   end)
|> Repo.transaction()
```
```

- [ ] **Step 7: Commit**

```bash
git add knowledge/spring_boot.md knowledge/express.md knowledge/gin.md knowledge/echo.md knowledge/actix.md knowledge/phoenix.md
git commit -m "feat: add CRUD patterns and call hierarchy to Java/JS/Go/Rust/Elixir knowledge files"
```

---

### Task 10: Add frontend-specific notes to frontend knowledge files

**Files:**
- Modify: `knowledge/nextjs.md`
- Modify: `knowledge/nuxt.md`
- Modify: `knowledge/flutter.md`

- [ ] **Step 1: Add frontend note and BFF patterns to nextjs.md**

Append to `knowledge/nextjs.md`:

```markdown

## CRUD操作パターン

> Next.js はフロントエンドフレームワークのため、エンティティに対する直接的なCRUD操作は
> サーバーサイド（バックエンドAPI）で行われる。ただし、API Route (Route Handlers) や
> Server Actions を使ったBFFパターンでは、Next.js 内でDB操作を行う場合がある。

### API Route / Server Actions でのDB操作（BFFパターン）
- Prisma, Drizzle 等のORMをNext.js内で直接使用するケースがある
- この場合は Express.js のknowledge（Prisma/TypeORM/Sequelize）のCRUD操作パターンを参照すること

### Server Actions
| CRUD | メソッド/パターン |
|------|-----------------|
| Create | `'use server'` 関数内で `prisma.model.create(...)` |
| Update | `'use server'` 関数内で `prisma.model.update(...)` |
| Delete | `'use server'` 関数内で `prisma.model.delete(...)` |

## コール階層

> Next.js の BFF パターンでは、以下の経路でCRUD操作が行われる。
> CLAUDE.md / AGENTS.md に記載がある場合はそちらを優先する。

### パターン1: API Route → Service → Model
```typescript
// app/api/orders/route.ts
export async function POST(req: Request) {
    const data = await req.json();
    return Response.json(await orderService.createOrder(data));
}
```

### パターン2: Server Action → Service → Model
```typescript
// app/actions/order.ts
'use server'
export async function createOrder(data: FormData) {
    const order = await prisma.order.create({ data: ... });  // Order: Create
}
```
```

- [ ] **Step 2: Add frontend note and Nitro patterns to nuxt.md**

Append to `knowledge/nuxt.md`:

```markdown

## CRUD操作パターン

> Nuxt.js はフロントエンドフレームワークだが、Nitro サーバーエンジンにより
> server/api/ 内でDB操作を直接行うBFFパターンが一般的。
> この場合のCRUD操作パターンは以下を参照。

### Nitro Server Route でのDB操作
- Prisma, Drizzle, Knex 等のORMをNuxtサーバー内で使用するケースがある
- Express.js のknowledge（Prisma/TypeORM/Sequelize）のCRUD操作パターンを参照すること

## コール階層

> Nuxt.js の server/api/ ルートでは、以下の経路でCRUD操作が行われる。
> CLAUDE.md / AGENTS.md に記載がある場合はそちらを優先する。

### パターン1: Server Route → Model（直接操作）
```typescript
// server/api/orders.post.ts
export default defineEventHandler(async (event) => {
    const body = await readBody(event);
    const order = await prisma.order.create({ data: body });  // Order: Create
    return order;
});
```

### パターン2: Server Route → Service → Model
```typescript
// server/api/orders.post.ts
export default defineEventHandler(async (event) => {
    const body = await readBody(event);
    return await orderService.createOrder(body);
});
```
```

- [ ] **Step 3: Add frontend note to flutter.md**

Append to `knowledge/flutter.md`:

```markdown

## CRUD操作パターン

> Flutter はモバイル/Web フロントエンドフレームワークのため、エンティティに対するCRUD操作は
> バックエンドAPI経由で行われる。Flutter 側にはサーバーサイドのCRUD操作パターンは存在しない。
> バックエンドのフレームワーク（Laravel, Spring Boot, FastAPI等）のknowledgeを参照すること。

### ローカルDB操作（sqflite / Drift）
- オフラインキャッシュやローカルストレージ用途で Flutter 内でDB操作を行う場合がある

| CRUD | sqflite | Drift |
|------|---------|-------|
| Create | `db.insert('table', data)` | `into(table).insert(companion)` |
| Read | `db.query('table')`, `db.rawQuery('SELECT ...')` | `select(table).get()`, `(select(table)..where(...)).get()` |
| Update | `db.update('table', data, where: ...)` | `(update(table)..where(...)).write(companion)` |
| Delete | `db.delete('table', where: ...)` | `(delete(table)..where(...)).go()` |

## コール階層

> Flutter のコール階層は主にAPIクライアント経由のためサーバーサイドのknowledgeを参照。
> ローカルDB操作がある場合は以下のパターンを参照する。

### パターン1: Screen → Repository → API
```dart
// API経由（サーバーサイドのCRUD）
class OrderRepository {
    Future<Order> createOrder(OrderInput input) async {
        final response = await dio.post('/api/orders', data: input.toJson());
        return Order.fromJson(response.data);
    }
}
```

### パターン2: Screen → Repository → Local DB
```dart
// ローカルDB操作
class CacheRepository {
    Future<void> cacheOrder(Order order) async {
        await db.insert('orders', order.toMap());          // Order: Create (local)
    }
}
```
```

- [ ] **Step 4: Commit**

```bash
git add knowledge/nextjs.md knowledge/nuxt.md knowledge/flutter.md
git commit -m "feat: add frontend-specific CRUD notes to Next.js/Nuxt/Flutter knowledge files"
```

---

### Task 11: Run all tests and verify

**Files:** None (verification only)

- [ ] **Step 1: Run all tests**

Run: `cd /Users/go/work/github/rdra-analyzer && python -m pytest tests/ -v`
Expected: All 14 tests PASS (4 from Task 2 + 4 from Task 3 + 6 from Task 6)

- [ ] **Step 2: Verify all modules import cleanly**

Run: `cd /Users/go/work/github/rdra-analyzer && python -c "from analyzer.source_parser import SourceParser, EntityOperation, ParsedController; from gap.crud_analyzer import CrudAnalyzer; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Verify knowledge files are well-formed**

Run: `cd /Users/go/work/github/rdra-analyzer && python -c "from knowledge.loader import detect_and_load; ids, text = detect_and_load({'composer.json': 'laravel/framework'}); print(f'Detected: {ids}'); assert 'CRUD操作パターン' in text; print('Knowledge OK')"`
Expected:
```
Detected: ['laravel']
Knowledge OK
```

- [ ] **Step 4: Verify backward compatibility — analyze with no entity_operations**

Run: `cd /Users/go/work/github/rdra-analyzer && python -c "
from gap.crud_analyzer import CrudAnalyzer
from rdra.information_model import Entity
analyzer = CrudAnalyzer()
entities = [Entity(name='ユーザー', class_name='User', attributes=['id', 'name'])]
statuses, gaps = analyzer.analyze(entities, [], [], [])
print(f'Statuses: {len(statuses)}, Gaps: {len(gaps)}')
assert len(statuses) == 1
assert len(gaps) == 4  # all CRUD missing
print('Backward compatibility OK')
"`
Expected:
```
Statuses: 1, Gaps: 4
Backward compatibility OK
```
