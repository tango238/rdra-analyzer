# Entity-First CRUD Detection Design

## Overview

CRUD操作の検出を、HTTPメソッドベースの表面的な判定から、エンティティのソースコードを起点としたボトムアップ解析に改善する。

### 背景・課題

現状の `CrudAnalyzer` は以下の3手法でCRUD操作を検出している:

1. APIルートのHTTPメソッド (`POST → Create`, `GET → Read` 等)
2. 操作シナリオのアクションキーワード (`"作成"`, `"削除"` 等)
3. ユースケース関連ルートのHTTPメソッド

いずれもルートのURLパターンとエンティティ名の文字列マッチに依存しており、**コントローラー内部で複数エンティティを間接的に操作しているケース**を検出できない。

例: 注文作成API (`POST /orders`) が内部で在庫 (`Stock`) の更新や決済 (`Payment`) の作成も行っている場合、Stock の Update と Payment の Create が検出漏れする。

### 解決方針: Entity-First Bottom-Up

エンティティのモデル/データアクセス層のソースコードを読み取り、CRUD操作を検出。その呼び出し元をコントローラーまで遡って追跡する。フレームワークごとのknowledgeファイルにCRUDメソッドパターンとコール階層を定義し、LLMの解析精度を向上させる。

---

## 1. Knowledgeファイルの拡張

### 対象

全15ファイル (`knowledge/*.md`)

**バックエンド系** (CRUDメソッドパターン + コール階層の両方を追加):
laravel, rails, django, fastapi, spring_boot, express, gin, echo, actix, phoenix

**フロントエンド系** (APIクライアント側のため、CRUDメソッドパターンは「該当なし — サーバーサイドのknowledgeを参照」と明記。コール階層はBFF/API Routeがある場合のパターンのみ記載):
nextjs, nuxt, flutter

### 追加セクション

各knowledgeファイルに以下の2セクションを追加する。

#### 1.1 CRUDメソッドパターン

フレームワークのORM/データアクセス層で、各CRUD操作に対応するメソッド/パターンを表形式で定義。

セクション冒頭に以下の優先度指示を記載:

```
> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にCRUD操作パターンや
> データアクセス層の規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの一般的なパターンであり、フォールバックとして参照する。
```

**Laravel の例:**

| CRUD | Eloquent Model | Query Builder |
|------|---------------|---------------|
| Create | `Model::create([...])`, `new Model(); $model->save()`, `Model::insert([...])` | `DB::table('x')->insert([...])` |
| Read | `Model::find($id)`, `Model::where(...)->get()`, `Model::all()`, `Model::first()`, `Model::paginate()` | `DB::table('x')->get()`, `DB::table('x')->find($id)` |
| Update | `$model->update([...])`, `$model->save()` (既存), `Model::where(...)->update([...])` | `DB::table('x')->where(...)->update([...])` |
| Delete | `$model->delete()`, `Model::destroy($id)`, `Model::where(...)->delete()`, `$model->forceDelete()` | `DB::table('x')->where(...)->delete()` |

**Spring Boot の例:**

| CRUD | JPA Repository | EntityManager |
|------|---------------|---------------|
| Create | `repository.save(new Entity(...))`, `repository.saveAll(list)` | `em.persist(entity)` |
| Read | `repository.findById(id)`, `repository.findAll()`, `repository.findBy*()` | `em.find(Entity.class, id)`, `em.createQuery(...)` |
| Update | `repository.save(existingEntity)` (IDあり), `@Modifying @Query(...)` | `em.merge(entity)` |
| Delete | `repository.delete(entity)`, `repository.deleteById(id)` | `em.remove(entity)` |

#### 1.2 コール階層

コントローラーからエンティティCRUD操作に至る典型的な呼び出し経路を、パターン別にコード例付きで定義。

セクション冒頭に以下の優先度指示を記載:

```
> **注意**: 対象プロジェクトの CLAUDE.md または AGENTS.md にアーキテクチャ構成や
> レイヤー間の呼び出し規約が記載されている場合は、そちらを優先すること。
> 以下はフレームワークの典型的なパターンであり、フォールバックとして参照する。
```

**パターン一覧:**

| パターン | 経路 | 典型的なプロジェクト |
|---------|------|-------------------|
| 直接操作 | Controller → Model | 小〜中規模 (Laravel, Rails等) |
| Service層 | Controller → Service → Model | 中〜大規模 |
| Repository層 | Controller → Service → Repository → Model | DDD/クリーンアーキテクチャ (Spring Boot等) |
| Event/Job | Controller → Event/Job → Model | 非同期処理、Cascade |

---

## 2. データ構造

### 2.1 EntityOperation (新規)

`analyzer/source_parser.py` に追加。

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
    call_chain: list[str]      # コール階層 (例: ["OrderController.store", "OrderService.createOrder"])
```

### 2.2 ParsedController の拡張

```python
@dataclass
class ParsedController:
    # ... 既存フィールド ...
    entity_operations: dict[str, list[EntityOperation]] = field(default_factory=dict)
    # メソッド名 → そのメソッドから到達するエンティティ操作リスト
```

### 2.3 parse_repo 戻り値の拡張

```python
return {
    "routes": routes,
    "controllers": controllers,
    "models": models,
    "pages": pages,
    "entity_operations": entity_operations,  # 新規追加
    "project_context": ctx,
}
```

---

## 3. LLM抽出ステップ

### 3.1 `_extract_entity_operations_with_llm`

`source_parser.py` に新メソッドを追加。モデル抽出(`_extract_models_with_llm`)の後に実行し、抽出済みエンティティ一覧をプロンプトに含める。

**入力**: `repo_path`, `context_text`, `models: list[ParsedModel]`
**出力**: `list[EntityOperation]`

**プロンプトの優先順位指示:**
```
CRUD操作の判定にあたっては、以下の優先順位で情報を使用してください:
1. CLAUDE.md / AGENTS.md に記載されたアーキテクチャ・規約（最優先）
2. プロジェクトの実際のソースコード
3. フレームワーク知識（上記が不明確な場合のフォールバック）
```

**プロンプトの解析指示:**
1. 各エンティティのモデル/エンティティクラスのソースコードを確認
2. そのエンティティに対するCreate/Read/Update/Deleteをプロジェクト全体から検出 (Controller, Service, Repository, Job, EventListener等)
3. 各操作の呼び出し元をControllerメソッドまで遡って追跡
4. 1つのControllerメソッドが複数エンティティを操作している場合、すべて記録

**LLMレスポンスのJSON形式:**
```json
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
    }
  ]
}
```

### 3.2 エンティティ数が多い場合のバッチ分割

エンティティ数が多いプロジェクト（目安: 20件超）では、1回のLLM呼び出しで全エンティティの操作を網羅的に抽出すると精度が下がるリスクがある。以下の戦略でバッチ分割する:

- エンティティリストを20件ごとにバッチ分割
- バッチごとに `_extract_entity_operations_with_llm` を呼び出す
- 結果をフラットリストに結合

```python
ENTITY_BATCH_SIZE = 20

def _extract_entity_operations_with_llm(self, repo_path, context_text, models):
    if len(models) <= ENTITY_BATCH_SIZE:
        return self._extract_entity_operations_batch(repo_path, context_text, models)

    all_operations = []
    for i in range(0, len(models), ENTITY_BATCH_SIZE):
        batch = models[i:i + ENTITY_BATCH_SIZE]
        operations = self._extract_entity_operations_batch(repo_path, context_text, batch)
        all_operations.extend(operations)
    return all_operations
```

バッチ分割はLLM呼び出し回数が増えるトレードオフがあるが、精度を優先する。

### 3.3 `_extract_entity_operations_with_api` (フォールバック)

Anthropic APIのみモード用フォールバック。コンテキスト情報と `ParsedController`/`ParsedModel` のデータから推定。

### 3.4 `_attach_operations_to_controllers`

`EntityOperation.call_chain` の先頭要素からコントローラー名・メソッド名を抽出し、対応する `ParsedController.entity_operations` に紐付ける補助メソッド。

### 3.5 parse_repo 内の呼び出し順序

```python
routes = self._extract_routes_with_llm(repo_path, context_text)
controllers = self._extract_controllers_with_llm(repo_path, context_text)
models = self._extract_models_with_llm(repo_path, context_text)
pages = self._extract_pages_with_llm(repo_path, context_text)
entity_operations = self._extract_entity_operations_with_llm(
    repo_path, context_text, models
)
self._attach_operations_to_controllers(controllers, entity_operations)
```

---

## 4. CrudAnalyzer の変更

### 4.1 検出の優先順位

```
1. EntityOperation（ソースコード解析ベース）  ← 新規・最優先
2. アクションキーワード（シナリオテキスト）    ← 既存・フォールバック
3. HTTPメソッド（ルートパターン）              ← 既存・フォールバック
4. ユースケース関連ルートのHTTPメソッド        ← 既存・フォールバック
```

### 4.2 シグネチャ変更

```python
def analyze(
    self,
    entities: list[Entity],
    routes: list[ParsedRoute],
    scenarios: list[OperationScenario],
    usecases: list[Usecase],
    entity_operations: list[EntityOperation] = None,  # 追加
) -> tuple[list[EntityCrudStatus], list[CrudGap]]:
```

### 4.3 新メソッド `_check_entity_operations`

`EntityOperation` リストからエンティティクラス名で照合し、CRUD操作と証跡を記録する。

**全証跡の収集**: 既存コードは最初の1件のみ記録してスキップする設計だが、Entity-First アプローチでは「OrderController.store と ReturnController.store の両方が Stock を Update している」のように複数経路の証跡が重要になる。`_check_entity_operations` では `not status.has_xxx` の条件を外し、同一CRUD操作の全証跡を収集する。フラグは初回で立て、証跡は全件追加する。

```python
# 旧: 最初の1件のみ
if op.operation == "Create" and not status.has_create:
    status.has_create = True
    status.create_evidence.append(evidence)

# 新: 全件収集
if op.operation == "Create":
    status.has_create = True
    status.create_evidence.append(evidence)
```

既存の `_check_routes`, `_check_scenarios`, `_check_usecases` のフォールバック側は現行動作を維持する（重複証跡の抑制）。

証跡のフォーマット:
```
OrderController.store → OrderService.createOrder: Order::create([...])
```

### 4.4 既存ロジックの扱い

`_check_routes`, `_check_scenarios`, `_check_usecases` は削除せずフォールバックとして残す。
- `entity_operations` が空の場合への備え
- LLMが見落とした操作の補完

---

## 5. 変更ファイル一覧

| ファイル | 変更内容 |
|---------|---------|
| `knowledge/*.md` (全15ファイル) | CRUDメソッドパターン + コール階層セクション追加 |
| `analyzer/source_parser.py` | `EntityOperation` 追加、`_extract_entity_operations_with_llm` 追加、`_extract_entity_operations_with_api` 追加、`_attach_operations_to_controllers` 追加、`ParsedController` フィールド追加、`parse_repo` 戻り値拡張 |
| `gap/crud_analyzer.py` | `_check_entity_operations` 追加、`analyze` / `_analyze_entity` シグネチャ変更、検出優先順位変更 |
| `main.py` | `gap` コマンドで `entity_operations` を渡す |

## 6. 変更しないファイル

| ファイル | 理由 |
|---------|------|
| `rdra/information_model.py` | Entity データクラスは変更不要 |
| `analyzer/usecase_extractor.py` | ユースケース抽出は変更不要 |
| `analyzer/scenario_builder.py` | シナリオ構築は変更不要 |
| `rdra/viewer_template.py` | EntityCrudStatus の構造は不変のためビューア変更不要 |
| `knowledge/loader.py` | テキスト読み込みのみなので変更不要 |
| `llm/` | LLMプロバイダーの変更不要 |

## 7. 後方互換性

- `entity_operations` パラメータはデフォルト `None`
- `ParsedController.entity_operations` は `field(default_factory=dict)`
- `parse_repo` 戻り値の新キーは未使用コードに影響しない
- 既存のHTTPメソッド/キーワード判定はフォールバックとして完全に残る
