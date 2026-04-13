# Viewer CRUD Matrix Fix Design

## Overview

`feat/entity-crud-detection` ブランチで導入された `entity_operations` データを RDRA ビューアの UC×Entity マトリクスにも反映する。あわせて、LLM 抽出から漏れたケースに備えた防御的フォールバック層を追加し、`gap` コマンドと viewer の判定ロジックの一貫性を取り戻す。

## 背景

`feat/entity-crud-detection` は、ソースコードレベルで CRUD 操作を抽出する `entity_operations` 仕組みを追加した。`gap` コマンドはこの新ロジックを使い始めた一方、`rdra/viewer_template.py` の JavaScript 側は依然として古い HTTP メソッドベースの推定 (`_routeToCrud`) を使い続けている。

### 観測された問題

UC-019「パスワード再設定」で、関連エンティティ User が `Create` と表示される。実際にはパスワード更新なので `Update` が正しい。原因は2つの欠陥が重なっている:

1. **viewer ロジックの問題**: `_routeToCrud` は `POST → C` と決め打ち。UC-019 の関連ルート (`POST /api/v2/spotly/auth/remind`, `POST /api/v2/spotly/auth/updated`) はどちらも POST なので C となる。
2. **LLM 抽出の漏れ**: `Spotly\Auth\PasswordReminder\ApiController.remind` / `.updated` 由来の `entity_operations` が checkpoint に1件も無い。LLM 抽出時にこれらのコントローラーが追跡されなかった。

### スコープ判断の経緯

元の spec (`docs/superpowers/specs/2026-04-10-entity-crud-detection-design.md`) は viewer 変更を意図的に除外していた:

> `rdra/viewer_template.py` — EntityCrudStatus の構造は不変のためビューア変更不要

しかしこの判断は、viewer 内部の JS が独自の HTTP メソッドベース CRUD 推定を持っていることを見落としていた。本 spec は元 spec の未完成部分を補完するもの。

## ゴール

### 観測可能なゴール

UC-019「パスワード再設定」と同種ケース (POST だが意味は Update) が viewer マトリクスで `U` と表示される。

### 副次ゴール

- viewer の CRUD 判定と `gap` コマンドの判定が同一データ源 (`entity_operations`) に基づくようになる
- LLM 抽出が将来劣化しても、viewer は防御的ヒューリスティックで多くのケースを救える
- 動詞辞書がユニットテストで管理され、検出パターンが追加・改良しやすい

### 非ゴール

- 既存の `gap/crud_analyzer.py` の挙動変更
- `verify` / `scenarios` / `e2e` コマンドへの影響
- 全ての LLM 抽出漏れの撲滅 (Phase 3 はベストエフォート)

## アーキテクチャ

### データフロー (修正前 → 修正後)

```
parse_repo
  └─ entity_operations (List[EntityOperation])
       │
       ├──→ gap/crud_analyzer.py     (新ロジック使用 ✓)
       └──→ main.py:run_rdra         (checkpoint から読み込んで MermaidRenderer に渡す)
              └─ rdra/mermaid_renderer.py
                  ├─ rdra/crud_matrix.py (新規モジュール)
                  │   └─ compute_uc_entity_crud()
                  │        Tier 1: entity_operations から照合
                  │        Tier 2: コントローラー/メソッド名/パス トークンのヒューリスティック
                  │        Tier 3: HTTP メソッド (フォールバック)
                  └─ rdra/viewer_template.py
                       └─ DATA.uc_entity_crud (事前計算済みマトリクス)
                       └─ JS _ucEntityCrud(uc, entity) → Set 参照のみ
```

### 既存のデータ構造の制約

- `Usecase.related_routes` は `list[str]` で `"POST /api/v2/spotly/auth/remind"` 形式の文字列（`list[ParsedRoute]` ではない）
- `crud_matrix.py` 側で `"METHOD PATH"` から実 `ParsedRoute` を逆引きするために、`routes_by_key: dict[str, ParsedRoute]` を `{f"{r.method} {r.path}": r for r in routes}` で構築する
- 逆引き不発時は path/method からだけでも Tier 2 を試せるように、`compute_uc_entity_crud` は `route_str` をそのまま受けても動くフォールバックを持つ

### 設計判断: CRUD 判定ロジックの配置

| 案 | 内容 | 採否 |
|---|---|---|
| Python 側で事前計算 | `crud_matrix.py` で計算→DATA に埋め込み→JS は参照のみ | **採用** |
| JS 側で計算 | viewer JS に Tier 1/2/3 ロジックを書く | 不採用 |

採用理由:
- pytest で完結するためテスト容易性が高い
- viewer JS の責務が「表示」に純化される
- 将来 `gap` と共通化する余地がある (動詞辞書・マッチングロジック)

## モジュール: rdra/crud_matrix.py (新規)

### インターフェース

```python
from analyzer.source_parser import EntityOperation, ParsedRoute
from analyzer.usecase_extractor import Usecase

# 動詞→CRUD 辞書 (Tier 2 用)
VERB_TO_CRUD: dict[str, str]

def compute_uc_entity_crud(
    uc: Usecase,
    entity_class: str,
    entity_operations: list[EntityOperation],
    routes_by_key: dict[str, ParsedRoute],
) -> set[str]:
    """UC × Entity の CRUD セットを多段フォールバックで判定して返す。

    Tier 1: entity_operations のうち、call_chain[0] が UC の関連ルートの
            controller.action と一致し、かつ entity_class 一致するものを集約。
            UC.related_routes は "METHOD PATH" 形式の文字列なので、
            routes_by_key (キー: "METHOD PATH") で ParsedRoute を逆引きして
            controller / action を取得する。
    Tier 2: UC の関連ルートを使って:
            (a) 逆引きできた場合 ParsedRoute.action をトークン化
            (b) 逆引き不発時は path 末尾セグメントをトークン化
            得たトークンを VERB_TO_CRUD で照合。
    Tier 3: HTTP メソッドベース (POST=C, GET=R, PUT/PATCH=U, DELETE=D)。

    Returns: {"C", "R", "U", "D"} のサブセット
    """
```

補助関数:

```python
def build_uc_entity_crud_index(
    usecases: list[Usecase],
    entity_operations: list[EntityOperation],
    routes: list[ParsedRoute],
) -> dict[str, dict[str, list[str]]]:
    """全 UC × 全関連 Entity (uc.related_entities) の CRUD を一括計算する。

    内部で routes_by_key を1度だけ構築し、各 (uc, entity) ペアに
    compute_uc_entity_crud を適用する。

    Returns: {uc_id: {entity_class: ["C","U", ...]}}
    """

def _build_routes_index(routes: list[ParsedRoute]) -> dict[str, ParsedRoute]:
    """{"METHOD PATH": ParsedRoute} の dict を構築。

    キー形式は usecase_extractor が UC.related_routes に詰める文字列と一致させる。
    """

def _tokenize(text: str) -> list[str]:
    """camelCase / snake_case / kebab-case を小文字 token のリストに分解。

    "passwordUpdate" → ["password", "update"]
    "password_reset" → ["password", "reset"]
    "/api/v2/users/destroy" → ["api", "v2", "users", "destroy"]
    """

def _normalize_op_to_chars(operation: str) -> list[str]:
    """'Create' → ['C'], 'Create/Update' → ['C', 'U']"""
```

### 動詞辞書の初期値

```python
VERB_TO_CRUD = {
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
```

辞書は最小限の高確度ワードから始め、誤検出が出るたびに精査する。

## モジュール: rdra/viewer_template.py (改修)

### `generate_viewer_html` シグネチャ拡張

```python
def generate_viewer_html(
    project_name: str,
    generated_at: str,
    data_json: str,         # 既存
    mermaid_sources: str,   # 既存
) -> str:
```

シグネチャは変更しない。代わりに `data_json` の中身に新キーを追加:

- `data_json` JSON に `entity_operations` (詳細パネル表示用) と `uc_entity_crud` (事前計算済みマトリクス) が含まれる前提

### JS 関数の修正

新規:
```javascript
function _ucEntityCrud(uc, entityClassName) {
  // DATA.uc_entity_crud から参照するだけ
  return new Set(((DATA.uc_entity_crud||{})[uc.id]||{})[entityClassName] || []);
}

function _ucCrud(uc) {
  // UC の全 related_entities にわたる CRUD 集合 (UC 一覧バッジ用)
  const all = new Set();
  const ucMap = (DATA.uc_entity_crud||{})[uc.id] || {};
  Object.values(ucMap).forEach(arr => arr.forEach(c => all.add(c)));
  if (all.size > 0) return all;
  // フォールバック (uc_entity_crud が無い古い viewer 用)
  return _routeToCrud(uc.related_routes||[]);
}
```

修正対象 (現状 `_routeToCrud(u.related_routes)` を直接呼んでいる箇所):

| 箇所 (行番号は現状) | 用途 | 置換先 |
|---|---|---|
| 545-572 | アクター×エンティティCRUDマトリクス | `_ucEntityCrud(u, entName)` |
| 596-604 | `_routeToCrud` 定義 | 残す (Tier 3 用、表示用途で他箇所からも使う) |
| 660-705 | UC×アクター集約マトリクス | UC 単位の CRUD は `_ucCrud(uc)` (新規、UC の全 entity を結合) |
| 714-755 | エンティティ × UC マトリクス | `_ucEntityCrud(u, entName)` |
| 885-896 | UC 一覧の CRUD バッジ | `_ucCrud(uc)` |
| 925-939 | エンティティ詳細パネル | `_ucEntityCrud(uc, cls)` |

具体的な箇所は実装時に grep で全箇所をリストアップしてから対応。

## ビューア生成パイプラインの統合

実際の修正対象は2ファイル:

### `main.py:run_rdra` (854-973行)

現状の checkpoint 読み込み箇所 (902-919行付近) に `entity_operations` の読み込みを追加し、`MermaidRenderer.render_all()` に渡す。

```python
# 既存
all_routes = [ParsedRoute(**r) ... for r in cp["routes"]]
all_controllers = [ParsedController(**c) ... for c in cp["controllers"]]

# 追加
from analyzer.source_parser import EntityOperation
all_entity_ops = [
    EntityOperation(**eo) if isinstance(eo, dict) else eo
    for eo in (cp.get("entity_operations") or [])
]

# render_all 呼び出し時に追加引数で渡す
saved_files = renderer.render_all(
    entities=entities,
    relationships=relationships,
    usecases=usecases,
    scenarios=scenarios,
    output_dir=output_dir,
    routes=all_routes,
    controllers=all_controllers,
    entity_operations=all_entity_ops,  # 新規
)
```

### `rdra/mermaid_renderer.py`

#### `render_all` シグネチャ拡張
```python
def render_all(
    self,
    entities: list[Entity],
    relationships: list[Relationship],
    usecases: list[Usecase],
    scenarios: list[OperationScenario],
    output_dir: Path,
    routes: list = None,
    controllers: list = None,
    entity_operations: list = None,  # 新規
) -> list[str]:
```

#### `_render_viewer` シグネチャ拡張と data dict 追加
現状 (200-263行) の data dict に2キー追加:

```python
data = {
    # ... 既存キー ...
    "entity_operations": [
        {
            "entity_class": op.entity_class,
            "operation": op.operation,
            "method_signature": op.method_signature,
            "source_file": op.source_file,
            "source_class": op.source_class,
            "source_method": op.source_method,
            "call_chain": op.call_chain,
        }
        for op in (entity_operations or [])
    ],
    "uc_entity_crud": crud_matrix.build_uc_entity_crud_index(
        usecases=usecases,
        entity_operations=(entity_operations or []),
        routes=(routes or []),
    ),
}
```

その後 `data_json = json.dumps(data, ...)` → `generate_viewer_html(data_json=...)` (既存処理のまま)。

## テスト戦略

### 新規ファイル: `tests/test_crud_matrix.py`

| テストケース | 検証内容 |
|---|---|
| `test_tier1_entity_operations_match` | call_chain[0] が UC の controller.action と一致 → CRUD 集約 |
| `test_tier1_entity_class_filter` | 別 entity_class の操作は除外 |
| `test_tier1_multiple_operations_aggregated` | Create と Update 両方ある場合は両方返す |
| `test_tier1_create_update_split` | `Create/Update` は C と U に分解される |
| `test_tier2_verb_update` | `update`/`updated`/`edit` などが U |
| `test_tier2_verb_delete` | `destroy`/`delete`/`remove` などが D |
| `test_tier2_verb_create` | `create`/`store`/`register` などが C |
| `test_tier2_verb_read` | `show`/`index`/`list` などが R |
| `test_tier2_camelcase_action` | `passwordUpdate` → U |
| `test_tier2_snake_case_action` | `password_reset` → U |
| `test_tier2_token_match_documents_known_overreach` | `updateLog` をトークン分解すると `["update","log"]` で `update` がヒット → U として検出する。これは仕様 (動詞含有メソッドは関連エンティティの U として扱う) であることをテストで明示する |
| `test_tier2_no_substring_false_positive` | `updates_count` のような変数めいた名前が部分文字列マッチ ("update" を含むだけ) で誤検出されないこと。トークン分解により `["updates","count"]` で `updates` は辞書未登録なら U にならない |
| `test_tier3_http_method_fallback` | tier1/2 不発時 HTTP メソッドベース |
| `test_uc019_password_reset_returns_update` | UC-019 fixture で U が返る回帰テスト |
| `test_uc_with_no_routes_returns_empty` | 関連ルート無し → 空 set |
| `test_priority_tier1_skips_tier2` | tier1 で結果が出れば tier2 は実行しない |
| `test_priority_tier2_skips_tier3` | tier2 で結果が出れば tier3 は実行しない |
| `test_build_index_full_pipeline` | `build_uc_entity_crud_index` が全 UC×Entity を一括計算 |

### TDD 順序

1. `test_crud_matrix.py` を全件 RED で書く
2. `crud_matrix.py` を実装して全件 GREEN
3. リファクタ
4. 既存 13 テスト + 新規 18 テスト = **31 テスト全 PASS** を確認

## LLM 抽出改善 (Phase 3, 並行作業)

### 調査ステップ (~30分)

`roomport/app/Http/Controllers/Spotly/Auth/PasswordReminder/ApiController.php` を読み、`remind` / `updated` の実装を確認:

| 調査結果 | 判定 | 対応 |
|---|---|---|
| **A**. User::save() 等を直接呼んでいる | LLM が拾えるはず → 拾えていない | prompt 強化 (網羅性指示) |
| **B**. PasswordResetService 経由 | call_chain 追跡不足 | prompt の階層追跡指示を強化 |
| **C**. Laravel `Password::sendResetLink()` facade 経由 | knowledge 不足 | `knowledge/laravel.md` に facade パターン追加 |
| **D**. 別エンティティ (`PasswordResetToken` 等) で User 自体は触らない | 検出漏れではない | 修正不要 (Tier 2 ヒューリスティックが救う) |

### 対処内容

- **A**: `analyzer/source_parser.py` の `_extract_entity_operations_with_llm` の prompt に「**全コントローラーメソッドを網羅すること**」と明示
- **B**: 同 prompt に「Service / Repository / Helper クラス内の操作も追跡し、call_chain は必ず Controller method を含めること」と明示
- **C**: `knowledge/laravel.md` の CRUD メソッドパターンに facade 行を追加:
  ```
  | Update | Password::sendResetLink([...]) | (パスワードリセット系 facade) |
  | Update | Auth::user()->update([...])    | (認証ユーザー直接更新) |
  ```
- **D**: 修正不要

### LLM 抽出側のテスト

`tests/test_source_parser_prompt.py` (新規) または既存ファイル拡張:
- prompt 文字列に網羅性キーワードが含まれることを確認
- knowledge 読み込み時に追加パターンが含まれることを確認

LLM 呼び出し自体はモック。

## 検証計画

### Phase 別作業順序と所要時間

| Phase | 作業 | 時間 | LLM 呼び出し |
|---|---|---|---|
| 1 | TDD で `crud_matrix.py` | 2h | 0 |
| 2 | viewer 統合 + `rdra` 単独再生成で確認 | 1〜2h | 0 |
| 3 | LLM 抽出改善 (調査 + 修正 + テスト) | 半日 | テスト時の少量 |
| 4 | フル analyze 再実行 + 最終確認 | 1.5h 待機 + 30分確認 | 数百件 |
| **合計** | | **約 1.5 日** | |

### 成功基準 (定量)

| 指標 | 現在 | 目標 |
|---|---|---|
| ユニットテスト数 | 13 PASS | 31+ PASS |
| viewer UC-019 関連エンティティ User の CRUD | C (誤) | U (正) |
| viewer UC-019 関連エンティティ SpotlyCustomer の CRUD | C (誤) | U (正) |
| 平均 CRUD 網羅率 (`gap` 出力) | 70.4% | 微増 (Phase 3 が成功した場合) |
| PasswordReminder 由来 entity_operations 件数 | 0 | >0 (Phase 3 が成功した場合) |

### 成功基準 (定性)

- Tier 2 ヒューリスティックが効くケースをスポットチェック (5 UC ほど目視)
- ヒューリスティックの誤検出が顕著でないことをスポットチェック

## リスクと対応

| リスク | 対応 |
|---|---|
| Tier 2 動詞辞書が過剰検出 | 最小辞書から開始。誤検出が出たらユニットテストで明示 |
| Phase 3 後の analyze が現状より遅くなる (prompt 強化で turn 増) | timeout 余裕を見る。失敗しても resume 可能 |
| viewer JS の `_routeToCrud` 直接呼びを見落とす | grep で全箇所列挙してチェックリスト管理 |
| Phase 4 の analyze エラー | checkpoint resume |
| `crud_matrix` モジュールが既存 import 構造と循環依存 | `rdra/crud_matrix.py` は `analyzer.*` のみ依存。`gap` は触らない (将来統合は別タスク) |

## コミット粒度

1コミット1論点で分け、レビューしやすくする:

1. `feat: add crud_matrix module with tier-based detection` (+ 18 tests)
2. `feat: pre-compute uc_entity_crud in viewer build`
3. `refactor: viewer JS uses pre-computed crud matrix`
4. `feat: improve LLM entity_operations extraction prompt` (Phase 3, 調査結果次第)
5. `docs: update knowledge/laravel.md with facade patterns` (Phase 3, 調査結果次第)

## 変更ファイル一覧

| ファイル | 変更内容 |
|---|---|
| `rdra/crud_matrix.py` | **新規**: Tier 1/2/3 多段フォールバック CRUD 判定 |
| `tests/test_crud_matrix.py` | **新規**: 18 テストケース |
| `rdra/viewer_template.py` | JS の `_routeToCrud` 直接呼びを `_ucEntityCrud` 経由に置換 (約6〜9箇所) |
| `rdra/mermaid_renderer.py` | `render_all` / `_render_viewer` シグネチャに `entity_operations` 追加、`data` dict に `uc_entity_crud` / `entity_operations` キー追加 |
| `main.py` (`run_rdra`) | checkpoint から `entity_operations` を読み込んで `render_all` に渡す |
| `analyzer/source_parser.py` | (Phase 3, 調査結果次第) `_extract_entity_operations_with_llm` の prompt 強化 |
| `knowledge/laravel.md` | (Phase 3, 調査結果次第) facade パターン追加 |
| `tests/test_source_parser_prompt.py` | (Phase 3, 任意) prompt 内容のユニットテスト |

## 後方互換性

- `data_json` の新キー `uc_entity_crud` / `entity_operations` は古い viewer.html (再生成前) で参照されないので無害
- viewer JS は `(DATA.uc_entity_crud || {})` のように安全に参照
- 既存の `_routeToCrud` 関数は削除せず Tier 3 として残る
- 既存 13 テストはそのまま PASS
- `gap/crud_analyzer.py` は無変更

## 作業ブランチ

- このまま `feat/entity-crud-detection` で続行
- 既存 worktree `feature/analyze-parallel` (analyze 並行化対応) は無関係
