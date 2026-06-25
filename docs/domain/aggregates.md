# Aggregates

> Phase 5 / DDD — rdra-analyzer の集約設計。4つのルール（不変条件を境界内で保護 / 小さく / 他集約は id 参照 / 結果整合）に基づく。
> [bounded-contexts.md](bounded-contexts.md) の 6 BC、[context-map.md](context-map.md) の Shared Kernel / PL / ACL を踏まえる。

## 仕分けの結論（Right-Sizing）

| 種別 | 要素 | 理由 |
|------|------|------|
| **振る舞い Aggregate** | ユースケース・エンティティ・実績シナリオ・業務フロー・解析セッション | 不変条件＋操作を持つ整合境界 |
| **Audit Aggregate**（追記専用・不変） | 棄却ログ（`RejectedUsecase`）・矛盾（`Conflict`） | UC を id 参照する記録。BC・ライフサイクルが UC と異なるため分離 |
| **Projection / Read Model**（集約でない） | システム境界・情報モデル・状態遷移・ビジネスポリシー・CRUDギャップ | 確定層から決定的に導出。不変条件なし・再生成可能・確度=derived・所有者なし |
| **Value Object** | 確度（`Confidence`）・APIエンドポイント・画面 | 属性を表す不変オブジェクト。UC が id 参照 |

> **Rule 3 はコードで既達**: `Usecase.related_routes/_controllers/_entities/_views/_pages` は全て文字列 ID 参照（オブジェクト参照でない）。

---

## 振る舞い Aggregate

### ユースケース（UseCase） — BC ① 要求モデル抽出 ★Core

- **Root Entity**: UseCase / **ID**: `UsecaseId`（`UC-001` / `UC-LE-001`）
- **構成要素**: `Confidence`(VO)・related_*（他集約への ID 参照リスト）・preconditions/postconditions(VO)
- **ビジネス不変条件**:
  - **確定 UC ⇔ コード証拠アンカー（route/controller/entity/page）が1つ以上存在**（#1 を集約ルール化）。違反 → 確定モデルに出さず棄却ログへ移送。
  - `confidence ∈ {confirmed, derived, inferred}`。コード証拠 1:1 = confirmed、合成（loop-e2e 由来）= inferred。
- **操作**: `確定する()` → `UCが確定された` / `棄却する(理由, 欠落証拠)` → `UCが棄却された`（棄却ログへ）/ `関連を再導出する()`（enrich・決定的）→ `関連が再導出された`
- **他 Aggregate 参照**: APIエンドポイント・エンティティ・画面（id のみ）
- **整合性**: 即時=自身の related_*/confidence。結果整合=Projection 群（確定変更を Domain Event で再生成）・棄却ログ（イベントで追記）

### エンティティ（Entity） — BC ①

- **Root Entity**: Entity / **ID**: `EntityClass`（クラス名）
- **構成要素**: `EntityOperation`（CRUD 操作・`Confidence` 付き・call_chain）
- **ビジネス不変条件**: 各 operation は当エンティティへの操作（entity_class 一致）。operation は静的抽出由来＝confidence=confirmed。
- **操作**: `操作を付与する(EntityOperation)`
- **整合性**: CRUD 完全性の判定は **Projection（CRUDギャップ）** が担う（集約内では持たない）。

### 実績シナリオ（OperationScenario） — BC ② 実績調停

- **Root Entity**: OperationScenario / **ID**: `ScenarioId`（`LE-...`）
- **構成要素**: `OperationStep`（順序付きステップ）・frontend_url・api_endpoint
- **ビジネス不変条件**: ステップは step_no 昇順。`usecase_id` で UC を参照。LE- は loop-e2e 所有＝冪等に扱う。
- **整合性**: ACL（`normalize_route`）で外部 PL（pending.json）から翻訳して構築。

### 業務フロー（BusinessFlow） — BC ③ 業務フロー協働 〔#5 未実装〕

- **Root Entity**: BusinessFlow / **ID**: `BusinessFlowId`
- **構成要素**: 想定フロー（確定 UC 群の連なり・id 参照）・承認状態・フィードバック履歴
- **ビジネス不変条件（状態機械）**: `想定 → レビュー → FB → 再想定 → 編集 → 承認 → 引き渡し`。
  - **承認は PdM のみ**（System は想定/再想定まで）。**引き渡しは承認後のみ**。
- **操作**: `想定する()`→`想定された` / `レビューする()` / `フィードバックする()`→`再想定へ` / `承認する(PdM)`→`承認された` / `引き渡す()`→`loop-e2e へ引き渡された`(PL)
- **他 Aggregate 参照**: 確定 UC（id のみ）
- **整合性**: 即時=自身の状態遷移。結果整合=loop-e2e への引き渡し（PL）。

### 解析セッション（AnalysisSession） — BC ①（横断・進行管理）

- **Root Entity**: AnalysisSession / **ID**: 出力ディレクトリ＋checkpoint
- **構成要素**: `phase`（parse→extract→done）・`completed_repos`・生成した参照事実（routes/pages/models/entity_operations）
- **ビジネス不変条件**: phase は単調進行。completed_repos は単調増加（再開可能＝冪等）。
- **役割**: 解析の進行を束ねる Process（Saga 的）。参照 VO（APIエンドポイント・画面）と エンティティを産出する。
- **整合性**: checkpoint への中間保存で再開可能性を担保。

---

## Audit Aggregate（追記専用・不変）

### 棄却ログ（RejectedUsecase） — BC ①

- **Root Entity**: RejectedUsecase / **ID**: 元 UC の `UsecaseId`
- **構成要素**: reason・missing_evidence（空アンカー名）
- **不変条件**: 追記専用・不変。「棄却＝破棄でなく記録」（検証フローの入力）。
- **他 Aggregate 参照**: 元 UC（id）。
- **整合性**: `UCが棄却された` イベントで結果整合的に追記。**救済フロー**（棄却＋loop-e2e 実績 → 再昇格）は未配線＝残課題。

### 矛盾（Conflict） — BC ② 実績調停

- **Root Entity**: Conflict / **ID**: （usecase_id, kind）
- **構成要素**: kind∈{actor_mismatch, controller_mismatch}・`code_value`（コード=真）・`actual_value`（実績）・detail
- **不変条件**: 追記専用・不変。「コードを真」＝UC は変更しない（要調査フラグのみ）。
- **他 Aggregate 参照**: マッチした UC（id）。
- **整合性**: `矛盾が検出された` イベントで結果整合的に追記（Shared Kernel の書き戻しとは独立）。

---

## Projection / Read Model（集約でない）

確定層（UseCase / Entity）から**決定的に導出**される派生投影。不変条件を持たず、いつでも再生成可能。確度=`derived`。所有者なし（UC を id 参照）。

| Projection | 由来 | コード |
|-----------|------|--------|
| システム境界 | 接点（画面）× 起点（エンドポイント） | `rdra/system_boundary.py`（#3） |
| 情報モデル | エンティティ＋リレーション | `rdra/information_model.py` |
| 状態遷移 | エンティティの状態 | `rdra/state_transition.py` |
| ビジネスポリシー | UC/コード | `rdra/business_policy.py` |
| CRUDギャップ | エンティティ × 操作 | `gap/crud_analyzer.py` |

→ openQuestion「システム境界 Aggregate と所有関係」は **「Aggregate ではなく Projection（所有者なし・UC を id 参照）」** で解消。

## Value Object

- **確度（Confidence）**: `confirmed | derived | inferred`。Shared Kernel（①↔②）。`confidence.py`。
- **APIエンドポイント（ApiEndpoint）**: method＋path。解析セッションが産出する確定事実。UC が id 参照。
- **画面（Screen）**: route_path＋component。同上。

---

## 整合性まとめ（Rule 4: 結果整合）

| トリガー（Domain Event） | 即時整合（同一集約） | 結果整合（別集約・イベント経由） |
|--------------------------|----------------------|----------------------------------|
| UCが確定された | UseCase.confidence/related_* | Projection 群を再生成 |
| UCが棄却された | — | 棄却ログ（Audit）へ追記 |
| 実績が取り込まれた | OperationScenario 構築（ACL） | Shared Kernel（analysis_result.json）へ救済/新規UC書き戻し |
| 矛盾が検出された | — | 矛盾（Audit）へ追記。UC は不変（コードを真） |
| 業務フローが承認された | BusinessFlow.状態 | loop-e2e へ引き渡し（PL） |

> 1トランザクション＝1集約変更。Projection・Audit・loop-e2e はすべて Domain Event 経由の結果整合。

## Anemic Domain Model チェック（--analyze 観点）

- **現状コードは関数型スタイル**: `partition_usecases`（#1）・`detect_conflicts`（#4）・各ジェネレータは dataclass に対する**モジュール関数**で、集約メソッドではない。
- **判定**: 純粋な Anemic 違反ではなく、**DMMF 的な関数型設計**（データ＝dataclass、振る舞い＝純粋関数）。Phase 9–11（型駆動）の方針と整合するため、無理にメソッド化しない。
- **ただし不変条件の所在は明示すべき**: UC の「確定⇔証拠あり」、BusinessFlow の状態機械は、Phase 10 で Smart Constructor / 型で「不正状態を表現不能」にするのが目標。

## 未解決の問い

- 救済フロー（棄却ログ ＋ loop-e2e 実績 → 再昇格）の所有者は ②（ACL 内）か、棄却ログ集約のメソッドか（#1 follow-on / Phase 9）。
- Shared Kernel `analysis_result.json` のスキーマ版管理者（① 単独か共同か）（Phase 6）。
- 業務フロー Aggregate の永続化形式と承認操作の置き場（CLI / ビューワー）（#5・Phase 9–11）。
