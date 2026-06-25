# Model ⇔ Implementation Sync

> `--analyze`（Phase 3 contexts）で発見した差異を判定・計画・実装し、モデルとコードを一致させる台帳。
> 由来: [bounded-contexts.md](bounded-contexts.md) の「コードベース突き合わせ」表＋「作業の北極星」、[event-storming.md](event-storming.md) の赤付箋、[discovery.md](discovery.md) のコア品質基準。
>
> **大前提**: このモデルは **as-built ではなく to-be（北極星）**。コード現状は Recall 寄り（全保持・新規 synthesize）で、
> 設計の Precision 寄りと逆。session decisions で「コードを今後作り変える北極星としてモデルを維持」と確定済み。
> したがって全差異の **権威はモデル**（＝コードがモデルに追いつく方向）。権威に争いは無く、論点はスコープと順序。

## 状態（このセッション）

台帳と詳細 plan を確定。**実装はユーザー承認後に着手**（次セッション）。承認時の推奨順序: **#2 → #1 → #4**（確度ラベルが棄却ログ・矛盾検出の基盤）、**#6 は独立**でいつでも着手可、**#3 / #5 / #7 は後続**。

## 差異台帳

| # | 由来phase | 種別 | 権威 | 決定（何をどう実装するか） | 状態 | commit |
|---|-----------|------|------|---------------------------|------|--------|
| 1 | storming/contexts | gap | model | コード証拠なき UC を確定モデルから棄却し棄却ログへ（opt-in `--strict`）。独立 `RejectedUsecase` 型 | **done**（未コミット） | — |
| 2 | contexts | gap | model | 抽出物に確度ラベル（`confidence` 三値）を付与。確定/派生/推論を区別 | **done**（未コミット） | — |
| 3 | contexts | gap | model | システム境界図の生成（接点＝画面 × 起点＝エンドポイントの対応）。決定的・LLM 不要。`rdra` 出力に追加 | **done**（未コミット） | — |
| 4 | storming/contexts | gap | model | reconcile に矛盾検出＋要調査フラグ。マッチ UC と実績の actor/controller 不一致を別レポートへ（コードを真・UC 不変） | **done**（未コミット） | — |
| 5 | storming/contexts | gap | model | 業務フロー協働 BC（PdM 承認ループ）の新規構築 | pending | — |
| 6 | contexts | cleanup | model | `scenarios`/`verify`/`e2e` コマンド＋`scenario_verifier`/`e2e/`/playwright を撤去。`scenario_builder` は共有型として存置 | **done**（未コミット） | — |
| 7 | contexts | structure | model | コードの継ぎ目（Source/UseCase/Scenario/Reconciliation）を設計の BC 境界へ寄せる | pending | — |

> 状態凡例: `pending → planned → in-progress → done`（または `model-updated` / `deferred`）。
> 進捗: **#2 / #1 / #4 / #3 / #6 = done（未コミット）**。#5 / #7 = deferred（それぞれ Phase 5/9–11・Phase 4 mapping のモデル決定が前提）。全 126 passed。

---

## 差異の詳細

### #2 確度ラベル（confidence） — 基盤・低リスク・推奨着手点

- **発見**: 派生層に確度ラベルが必須（[bounded-contexts.md](bounded-contexts.md) L106）だが、`confidence`/`score` フィールドが皆無。全抽出物が等しく「確定」扱い。
- **コードの事実**:
  - `analyzer/usecase_extractor.py:19` `Usecase` — confidence/出自フィールド無し。`category` はあるが分類用（"loop-e2e" 等）。
  - `analyzer/source_parser.py:86` `EntityOperation` — confidence 無し。
  - 派生ジェネレータ（`rdra/information_model.py` / `state_transition.py` / `business_policy.py` / `gap/crud_analyzer.py`）も確度を持たない。
  - grep 確認: `confidence|score|reject` はソース（テスト除く）にヒット0。
- **権威と判断**: **model**。確定層（コード証拠＝高確度）と派生層（合成・推論＝確度ラベル必須）の区別はモデルの不変条件。コードが未追従。
- **計画**:
  - **目標**: 抽出物に確度を表現する型を追加。確定層（UC/エンティティ＝コード証拠）は `confirmed`、派生層（情報モデル/状態遷移/BP/CRUDギャップ/システム境界）は生成根拠の強さでラベル付け。
  - **方針分岐**（未決・要承認）:
    - **(A) 二値**: `confidence: Literal["confirmed", "derived"]`（確定 / 派生）。最小・明快。
    - **(B) 三値**: `confirmed`（コード証拠1:1）/ `derived`（確定層から決定的に導出）/ `inferred`（LLM 推論）。openQuestions「確度ラベルの値域」に対応。
    - **(C) 連続スコア**: `float 0.0–1.0`。柔軟だが閾値運用が必要、Precision 判定（#1）と相性が複雑。
    - → 推奨 **(B)**。Phase 5/10 の型設計と整合し、#1 の棄却判定（confirmed 未満を棄却候補に）に直結。
  - **影響ファイル**:
    - 変更: `analyzer/usecase_extractor.py`（`Usecase` に `confidence` 追加、デフォルト `"confirmed"`）、`analyzer/source_parser.py`（`EntityOperation`）、`main.py`（checkpoint シリアライズ `_*_to_dict` / ロード）、各 `rdra/*.py` 派生ジェネレータ（出力に確度付与）。
    - テスト: `tests/test_usecase_enrich.py` / `tests/test_entity_operation_parsing.py` / `tests/test_crud_*` にラベル検証を追加。
  - **リスク**: 低。フィールド追加＋デフォルト値で後方互換維持。checkpoint JSON のスキーマdrift に注意（ロード側で `.get("confidence", "confirmed")`）。
  - **スコープ外（残）**: 派生ジェネレータ（`rdra/*.py`）は Mermaid 図を出力し checkpoint に永続化しないため、確度付与＝可視化（④）の見せ方（色分け・凡例）として後続（#3 と合わせて）。エンティティ層（UC/EntityOperation）の確度＝#1/#4 が必要とする土台は完了。
- **採用**: **(B) 三値**（`confirmed`/`derived`/`inferred`）。新規 `confidence.py`（`Confidence` 型＋`rank()`/`coerce()`）。合成 UC-LE は `inferred`、静的抽出物は既定 `confirmed`。
- **実装結果**: ✅ 完了。新規 `confidence.py` ＋ `tests/test_confidence.py`（8 ケース）。変更: `usecase_extractor.py`/`source_parser.py`（フィールド追加）、`reconcile.py`（往復＋合成ラベル）、`main.py`（entity_operation 永続化）。全 **104 passed**（旧 96＋8）。`py_compile`・import スモーク・旧スキーマ既定値を確認。後方互換維持。**未コミット**。lint/mypy はローカル未導入のため CI 委譲。
- **モデル再整合**: ✅ [bounded-contexts.md](bounded-contexts.md) L106 の 🔴 を「解消」へ更新。openQuestions「確度ラベルの値域」を「三値で確定」として decisions に反映。

### #1 Precision 棄却 ＋ 棄却ログ — 最重要・高リスク

- **発見**: コア出力の正確性の柱。コードは Recall（全保持・dedup のみ、棄却概念なし、未マッチは新規 synthesize）で **設計と逆**（[bounded-contexts.md](bounded-contexts.md) L105）。
- **コードの事実**:
  - `analyzer/reconcile.py:344` `resolve_usecase` — `match_existing_usecase` → `_find_uc_by_facts` で当たらなければ **無条件に** `_synthesize_usecase`（`UC-LE-NNN`）を生成。棄却の枝が存在しない。
  - `_synthesize_usecase`（L315）は facts が薄くても（controller/component が空でも）UC を起こす＝根拠の強さを問わない。
  - 抽出本体（`usecase_extractor.py`）側も LLM 生成 UC をそのまま採用、コード証拠との照合で落とす機構なし。
- **権威と判断**: **model**。「根拠なき UC は確定モデルに出さない／ただし棄却＝破棄でなくログへ」は Core の不変条件（[discovery.md](discovery.md) L43–49）。
- **計画**:
  - **目標**: 抽出/reconcile で **証拠の連鎖が切れる UC を確定モデルから除外**し、棄却ログ（理由＋欠落した証拠）へ退避。確定モデルは confidence≥`derived` のみ。
  - **依存**: #2（confidence）が前提。棄却判定は「confidence が閾値未満 or 証拠連鎖断絶」で行う。
  - **方針分岐**（未決・要承認、openQuestion「棄却ログは独立 Aggregate か UC の状態か」）:
    - **(A) 独立棄却ログ**: `RejectionLog` 型＋別出力（`rejection_log.json`）。確定モデルと分離。検証フロー（実績救済 #4）の入力に使いやすい。
    - **(B) UC の状態**: `Usecase.status: Literal["confirmed", "rejected"]`。1コレクションで状態管理。実装は軽いが確定モデルのフィルタが各所に必要。
    - → **採用 (A) 独立棄却ログ**。discovery「2つのアウトプット（確定要求モデル / 棄却ログ）」と直接対応。Phase 5 集約設計の入力にもなる。
  - **棄却の判定（実装）**: コード証拠アンカー（`related_routes`/`related_controllers`/`related_entities`/`related_pages`）が**1つも無い**UC を「証拠連鎖が切れている」とみなし棄却。決定的・LLM 不使用。欠落証拠（空アンカー名）を記録。
  - **影響ファイル（実装済み）**: 新規 `analyzer/rejection_log.py`（`RejectedUsecase` 型＋`partition_usecases()`/`has_code_evidence()`/`missing_evidence()`＋往復シリアライズ）、`main.py`（`analyze` に opt-in `--strict`：partition→`rejection_log.json` 出力→確定モデルを confirmed のみに）、`tests/test_rejection_log.py`（8 ケース）。
  - **リスク対処**: **opt-in `--strict`**（既定 off）。デフォルトは現行 Recall 挙動を完全維持＝既存 diff・下流（図/ビューワー/gap）に影響なし。Precision は明示フラグで段階移行。
  - **スコープ外（残＝新しい赤付箋）**: ①**救済フロー**（静的棄却 ＋ loop-e2e 実績あり → 救済して確定）— reconcile が棄却ログを入力に再昇格する配線は #1 follow-on / #4 と合流。②抽出本体（`usecase_extractor`）での照合フィルタは今回未着手（現状アンカーは LLM 出力依存）。③棄却ログの可視化・棄却理由の自動分類。
- **実装結果**: ✅ 完了（コア＋opt-in 配線）。新規テスト 8 / 全 **112 passed**（104＋8）。`py_compile` 通過、`analyze --strict` フラグ登録確認。デフォルト挙動不変＝後方互換。**未コミット**。
- **モデル再整合**: ✅ [bounded-contexts.md](bounded-contexts.md) L105 を「実装済み（opt-in）」へ、[event-storming.md](event-storming.md) 赤付箋「棄却ログは破棄禁止」を解消注記へ。openQuestion「棄却ログ種別」を「独立型で確定」へ。救済フローを新しい未解決として明記。

### #4 矛盾検出 ＋ 要調査フラグ（reconcile）— 中リスク

- **発見**: reconcile に「静的で確定 ＋ 実績と矛盾 → コードを真・要調査フラグ」の枝が無い。未マッチは黙って新規 UC 化（[bounded-contexts.md](bounded-contexts.md) L110、[discovery.md](discovery.md) L58）。
- **コードの事実**:
  - `analyzer/reconcile.py:344` `resolve_usecase` の分岐は「既存に当たる / 当たらない（新規）」の2値のみ。「当たるが内容が食い違う」状態を検出しない。
  - 実績シナリオのステップ/期待結果と既存 UC の事後条件・関連を突き合わせる比較が無い。
- **権威と判断**: **model**。「矛盾時はコードを真、矛盾は要調査フラグで PdM 提示」はコア判断基準（[discovery.md](discovery.md) L58、「コア判断基準」）。
- **計画**:
  - **目標**: マッチした UC と実績 facts の不一致（例: 実績が叩く route が UC の related に無い、actor 相違）を検出し、UC を上書きせず `要調査` フラグ＋差分メモを付す。
  - **採用 (B) 別 `ConflictReport` 出力**（棄却ログ #1(A) と対称、確定モデルを汚さない）。
  - **矛盾の判定（実装）**: 誤検出を抑え根拠が明確な2種のみ — ① `actor_mismatch`（実績ステップのアクター ≠ UC 宣言アクター）、② `controller_mismatch`（実績ルートが checkpoint で解決するコントローラが UC の `related_controllers` と1つも重ならない＝別ハンドラを叩いた）。マッチ（`linked`）経路でのみ判定。UC は一切変更しない（コードを真）。
  - **影響ファイル（実装済み）**: 新規 `analyzer/conflict_report.py`（`Conflict` 型＋往復シリアライズ）、`analyzer/reconcile.py`（`detect_conflicts()`＋`ReconcileResult.conflicts`＋マッチ時に蓄積）、`main.py`（reconcile が `conflict_report.json` 出力＋件数表示）、`tests/test_conflict_report.py`（8 ケース）。
  - **リスク対処**: 中。matched 経路に比較を足すだけで既存リンク挙動は不変（`linked`/`created` 不変をテストで確認）。判定を2種に絞り過剰フラグを抑制。
  - **スコープ外**: 矛盾の自動修正は禁止（コードを真＝モデル側を触らない、提示のみ）。実績ステップ⇔UC 事後条件の意味的突き合わせは後続。
- **実装結果**: ✅ 完了。新規テスト 8 / 全 **120 passed**（112＋8）。`py_compile` 通過。既存 reconcile 挙動は不変（後方互換）。**未コミット**。
- **モデル再整合**: ✅ [bounded-contexts.md](bounded-contexts.md) L110 の 🟡 を「実装済み」へ更新。

### #3 システム境界の生成 — 中リスク・加算的

- **発見**: actor→UC 図が最も近いが、システム境界図（接点＝画面 × 起点＝エンドポイント）は出ない（[bounded-contexts.md](bounded-contexts.md) L108）。
- **コードの事実**: `rdra/usecase_diagram.py`（actor→UC）が近接。`enrich` の画面↔エンドポイント照合（[discovery.md](discovery.md) L25）が境界の素材を既に持つ＝**新規生成でなく既存照合の意味づけ**（[event-storming.md](event-storming.md) 赤付箋）。
- **権威と判断**: **model**。
- **計画**:
  - **目標**: enrich の照合結果（画面↔エンドポイント対応）から、アクター・接点（画面）・システム（エンドポイント群）の境界図を Mermaid 出力。
  - **採用**: `rdra` 配下の図種に追加（既存導線温存）。決定的生成（LLM 不要）＝派生層・確度 `derived`。
  - **生成内容（実装）**: アクター（境界の外）／subgraph「システム境界」内に 接点（`related_pages`∪`related_views`）と 起点（`related_routes`）／UC 内の対応で アクター→接点→起点 のエッジ（接点が無ければアクター→起点直結）。辺は重複排除・決定的（ソート済み）。
  - **影響ファイル（実装済み）**: 新規 `rdra/system_boundary.py`（`SystemBoundaryGenerator`）、`main.py`（`rdra` が `rdra/system_boundary.md` を追加出力）、`tests/test_system_boundary.py`（6 ケース）。
  - **リスク対処**: 中。加算的・既存 `render_all` に非干渉（別ファイル出力）。決定性をテストで担保。
  - **スコープ外**: 境界の対話的編集、確度の色分け凡例。
- **実装結果**: ✅ 完了。新規テスト 6 / 全 **126 passed**（120＋6）。`py_compile` 通過、サンプル Mermaid 出力確認。**未コミット**。
- **モデル再整合**: ✅ [bounded-contexts.md](bounded-contexts.md) L108 の 🟡 を「実装済み」へ更新。openQuestion「システム境界 Aggregate と所有関係（Phase 5）」は設計課題として残置。

### #5 業務フロー協働 BC（PdM 承認ループ）— 最大・新規

- **発見**: 丸ごと未実装。`rdra/activity_diagram.py` は 100% 自動生成で承認ゲートが無い（[bounded-contexts.md](bounded-contexts.md) L111、[event-storming.md](event-storming.md) E節）。
- **コードの事実**: `rdra/activity_diagram.py:10` `ActivityDiagramGenerator` はシナリオ→図の一方向変換のみ。想定→レビュー→FB→再想定→微調整→承認の状態機械が存在しない。
- **権威と判断**: **model**。確定者＝人間（PdM）の承認ループはモデルの中核イベント群（22–28）。
- **計画**:
  - **目標**: 確定 UC 群から業務フローを想定し、PdM 承認の状態（想定/レビュー/FB/再想定/編集/承認/引き渡し）を保持・遷移させる。承認済みを loop-e2e へ引き渡す成果物を出す。
  - **方針分岐**（未決・要承認）: 対話 UI の置き場 — (A) CLI 対話（承認/差し戻しをコマンドで）、(B) ビューワー（④）に承認操作を載せる。状態の永続化形式も要決定。
  - **影響ファイル**: 新規 `workflow/`（協働 BC 一式：状態機械＋永続化）、`main.py`（新サブコマンド群）、可視化連携。
  - **リスク**: **高**。新規・状態管理・対話。Phase 5（集約）/ Phase 9–11（型・ワークフロー）の設計を先に固めるべき。
  - **スコープ外**: テスト作成・E2E 実行（loop-e2e へ委譲＝BC 境界を越えない、[event-storming.md](event-storming.md) 赤付箋）。
- **実装結果**: 未着手。**先に Phase 5/9–11 を通すことを推奨**（sync 単独で着手すると設計負債）。
- **モデル再整合**: [bounded-contexts.md](bounded-contexts.md) L111 の 🔴。実装時に Phase 5 集約設計へ出戻り。

### #6 スコープ外コマンドの撤去（scenarios / verify / e2e）— 独立・破壊的

- **発見**: `scenarios`/`verify`/`e2e` が `main.py` に残存（非推奨表示付き）。Discovery でスコープ外決定済み（[discovery.md](discovery.md) L74–77、[bounded-contexts.md](bounded-contexts.md) L116）。
- **コードの事実**:
  - `main.py` の `@app.command`: `scenarios`(L675) / `verify`(L796) / `e2e`(L1421) が現存。`scenarios` は既に「reconcile を使え」と促し `--force` ガード付き。
  - 関連モジュール: `analyzer/scenario_builder.py` / `analyzer/scenario_verifier.py` / `e2e/`（`agent_loop.py` / `playwright_runner.py` / `scenario_executor.py`）。
  - **要注意の事実**: `scenarios` コマンドが `verifier._verify_step`（`scenario_verifier`）を参照（main.py:767）。撤去は依存順に。`reconcile.py` は `OperationScenario`/`OperationStep`/`pending_to_scenario` を `scenario_builder` から使う → **scenario_builder の型は reconcile が依存するため残す**（実績取り込みは残存決定）。
- **権威と判断**: **model**（スコープ外＝コードから除去）。ただし `reconcile`/`enrich` は実績取り込みとして残す。
- **計画**:
  - **目標**: 3コマンド＋純粋に E2E 実行用のモジュールを段階撤去。reconcile が依存する型（`scenario_builder` の dataclass 群）は維持。
  - **コード読解で判明した重要事実（naive plan を上書き）**: `scenario_builder` の `OperationScenario`/`OperationStep`/`ScenarioBuilder.save_to_json` は **analyze の主出力書き込み・rdra・gap・reconcile・`_load_analysis_result` が依存**＝中核インフラ。**撤去不可・存置**。さらに `all` コマンドのパート4が `run_e2e.callback` を呼ぶ＝`e2e` 撤去には `all` の再配線が必要（コード読解で新たに判明）。テストは削除モジュールを import していない（安全）。
  - **実施（実装済み）**: ① コマンド削除 `scenarios`/`verify`/`e2e`（main.py から計331行除去）。② 到達不能モジュール削除 `analyzer/scenario_verifier.py`・`e2e/`（`git rm`）。③ `all` コマンドからパート4（E2E）＋`--skip-e2e`/`--url` を除去。④ orphan 依存 `playwright` を `pyproject.toml`/`requirements.txt`/packages-include から除去。**`scenario_builder` は存置**。
  - **採用**: 一括（同一セッション・未コミット＝git で可逆）。コミット時に logical 単位へ分割可能。
  - **リスク対処**: 破壊的だが未コミット（`git restore` で可逆）。削除前に全被参照を grep し依存グラフを確定。削除後 import スモーク＋全 **126 passed**＋CLI コマンド一覧（9個）を確認。
- **実装結果**: ✅ 完了。残コマンド: config / analyze / reconcile / enrich / screens / rdra / gap / viewer / all。全 **126 passed**（不変＝後方互換）。`import main` OK。**未コミット**（staged 削除）。
- **モデル再整合**: ✅ [bounded-contexts.md](bounded-contexts.md) L116 を「撤去済み」へ更新。#7 の構造ズレ解消の第一歩（Scenario context は `scenario_builder` 型のみに縮小）。

### #7 コードの継ぎ目を BC 境界へ寄せる — 構造・大

- **発見**: コード実体の継ぎ目（Source / UseCase / Scenario / Reconciliation）が設計の BC 境界とズレ、特に「Scenario context」が厚く残る（[bounded-contexts.md](bounded-contexts.md) L117）。
- **権威と判断**: **model**。ただし #6（Scenario 系撤去）の後でないと評価できない＝**#6 の結果に従属**。
- **計画**: #6 完了後にディレクトリ構成を 4 BC（要求モデル抽出 / 実績調停 / 業務フロー協働 / 可視化）＋ Generic（llm / project_context）へ寄せる横断リファクタ。Phase 4（mapping）の関係種別確定を前提。
- **リスク**: 大（import 連鎖・横断移動）。単独セッションで一気にやらない。
- **実装結果**: **deferred**（#6 は完了済みで Scenario context は `scenario_builder` 型のみへ縮小。残る横断移動は **Phase 4 mapping の関係種別確定が前提**＝モデル側の決定待ち。sync の原則「モデルの抜けは該当フェーズへ出戻り、勝手に塗りつぶさない」に従い保留）。

---

## スコープ外・残課題（新しい赤付箋）

- 確度の **可視化**（色分け・凡例）— #2/#3 実装後の④可視化拡張。
- 棄却ログ・矛盾レポートの **PdM 向け提示 UI** — ④可視化拡張。
- #5 業務フロー協働 BC は **Phase 5/9–11 を先に通す**（型・集約・ワークフロー設計）。
- #7 構造リファクタは **#6 完了 ＋ Phase 4 mapping 確定**が前提。

## 未解決の問い（承認時に決める方針分岐）

- #2: 確度ラベルの値域 — 二値 / **三値(推奨)** / 連続スコア（openQuestion「確度ラベルの値域」と同一）。
- #1: 棄却ログは **独立型(推奨)** か UC の状態か（openQuestion「棄却ログ Aggregate 種別」）。さらに Precision 棄却を opt-in フラグで段階導入するか。
- #4: 要調査フラグの所在 — UC 属性 / **別レポート(推奨)**。
- #3: システム境界は独立コマンド / **rdra 図種に追加(推奨)**。
- #5: 承認ループの UI（CLI 対話 / ビューワー）と状態永続化形式。
- #6: 一括 / **段階撤去(推奨)**。
