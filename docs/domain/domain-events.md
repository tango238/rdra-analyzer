# Domain Events

> Phase 6 / DDD — rdra-analyzer のドメインイベント設計（命名・プロパティ・因果）。
> [event-storming.md](event-storming.md) の 28 イベント、[aggregates.md](aggregates.md) の集約、[context-map.md](context-map.md) の境界を踏まえる。
>
> **方針（確定）**: 受け渡しは **Enrichment**（イベントに必要データを同梱）。Event Sourcing は **業務フロー（#5）のみ ES 的**に履歴保持、他は再生成 or 追記ログ。
> **命名**: 和文過去形（モデル）⇄ 英 PascalCase 過去形（Phase 10 型・括弧内）。`occurredOn` は全イベント必須。
> **コードの現状**: 大半のイベントは関数実行に暗黙化され `occurredOn` 未スタンプ＝**実体化は to-be**。Audit 系は record（`RejectedUsecase`/`Conflict`）が既にイベントペイロードと一致＝実質 Enrichment 済み。

---

## BC ① 要求モデル抽出（Core）

発生元 Aggregate: 解析セッション / UseCase / Entity。Consumer は同一プロセスの後続ステージ（パイプライン進行）。

| イベント（和文 / 英） | トリガー | プロパティ（Enrichment） | Consumer |
|---|---|---|---|
| 解析が起動された / `AnalysisStarted` | PdM: 解析を起動する | `sessionId, repoPaths[], occurredOn` | 解析セッション |
| コンテキストが構築された / `ContextBuilt` | System | `sessionId, manifestSources[], occurredOn` | 抽出 |
| ルートが抽出された / `RoutesExtracted` | System | `sessionId, endpoints[]{method,path}, occurredOn` | UC候補生成 |
| モデルが抽出された / `ModelsExtracted` | System | `sessionId, entities[], occurredOn` | 情報モデル(Projection) |
| 画面が分析された / `ScreensAnalyzed` | System | `sessionId, screens[]{path,component}, occurredOn` | enrich / システム境界 |
| チェックポイントが保存された / `CheckpointSaved` | System | `sessionId, phase, completedRepos[], occurredOn` | 再開（冪等） |
| UC候補が生成された / `UsecaseCandidatesGenerated` | System: UC候補を生成する | `sessionId, candidateIds[], occurredOn` | コード証拠照合 |
| **UCが確定された** / `UsecaseConfirmed` 🎯 | System: UCを確定する | `ucId, confidence, evidenceAnchors[], occurredOn` | ④ Projection 再生成 |
| **UCが棄却された** / `UsecaseRejected` 🎯 | System: UCを棄却する | `ucId, reason, missingEvidence[], occurredOn` | **棄却ログ Audit** |
| 関連が再導出された / `RelationsReDerived` 🎯 | System: enrich | `ucIds[], occurredOn` | （決定的・冪等） |

**不変条件との対応**: `UsecaseConfirmed` は「確定 ⇔ `evidenceAnchors` が1つ以上」を満たすときのみ発行。違反は `UsecaseRejected`（→棄却ログ）へ分岐。

---

## BC ② 実績調停（Supporting / ACL）

発生元 Aggregate: 実績シナリオ / Conflict。inbound は loop-e2e から Published Language（ACL 翻訳）。

| イベント（和文 / 英） | トリガー | プロパティ（Enrichment） | Consumer |
|---|---|---|---|
| 実績シナリオが取り込まれた / `ActualScenarioIngested` | loop-e2e（PL→ACL） | `scenarioId, usecaseId?, steps[], frontendUrl, occurredOn` | 調停 |
| 新規UCが実績から生成された / `UsecaseSynthesizedFromActual` | System | `ucId(UC-LE-NNN), loopE2eId, confidence=inferred, occurredOn` | Shared Kernel 書き戻し |
| **棄却UCが実績で救済された** / `RejectedUsecaseRescued` 🎯 | System | `ucId, loopE2eId, occurredOn` | UC 再昇格（**#1 follow-on 未配線**） |
| **コードと実績の矛盾が検出された** / `ConflictDetected` 🎯 | System: 矛盾を検出する | `ucId, kind, codeValue（真）, actualValue, occurredOn` | **矛盾 Audit** |

**「コードを真」**: `ConflictDetected` は UC を変更しない。`codeValue` が真、`actualValue` は参考。要調査として矛盾 Audit へ追記のみ。

---

## BC ③ 業務フロー協働（Supporting）〔#5 未実装・ES 的〕

発生元 Aggregate: BusinessFlow（**唯一の Event Sourcing 対象**）。承認状態は下記イベントストリームの再生で復元。

| イベント（和文 / 英） | トリガー | プロパティ（Enrichment） | Consumer |
|---|---|---|---|
| 業務フローが想定された / `BusinessFlowProposed` | System | `flowId, ucIds[], occurredOn` | PdM レビュー |
| 業務フローがレビューされた / `BusinessFlowReviewed` | PdM | `flowId, by=PdM, occurredOn` | — |
| 業務フローにFBされた / `BusinessFlowFeedbackGiven` | PdM | `flowId, by=PdM, feedback, occurredOn` | 再想定 |
| 業務フローが再想定された / `BusinessFlowReProposed` | System | `flowId, occurredOn` | PdM レビュー |
| 業務フローが編集された / `BusinessFlowEdited` | PdM | `flowId, by=PdM, edits, occurredOn` | — |
| **業務フローが承認された** / `BusinessFlowApproved` ✅ | PdM: 承認する | `flowId, approver=PdM, occurredOn` | 引き渡し |
| 承認済みフローが引き渡された / `ApprovedFlowHandedOff` | System | `flowId, occurredOn` | **loop-e2e（PL）** |

**ES の根拠**: 「誰がいつ何を差し戻し/承認したか」は再解析で復元できない一度きりの PdM 判断＝履歴が真実。状態機械（想定→…→承認→引き渡し）は append-only ストリームの畳み込みで得る。承認・引き渡しの前提イベント（因果）を満たさない遷移は不正。

---

## BC ④ 可視化（Supporting）— Projection 再生成イベント

`UsecaseConfirmed` / `ModelsExtracted` 等を受けて派生投影（Read Model）を再生成する。状態を持たず冪等。

| イベント | プロパティ | 備考 |
|---|---|---|
| システム境界が特定された / `SystemBoundaryIdentified` | `sessionId, occurredOn` | 接点×起点の Projection（#3） |
| 情報モデル/状態遷移/BP/CRUDギャップ/ビューワーが生成された | `sessionId, occurredOn` | 各 Projection（確度=derived） |

---

## Event Flow（コンテキスト間）

```
loop-e2e ──ActualScenarioIngested (PL→ACL)──▶ ② 実績調停
   ② ──UsecaseSynthesized / RejectedUsecaseRescued (Shared Kernel 書き戻し)──▶ ① 要求モデル抽出
   ② ──ConflictDetected──▶ 矛盾 Audit（UC 不変・コードを真）
   ① ──UsecaseConfirmed──▶ ④ 可視化（Projection 再生成）
   ① ──UsecaseRejected──▶ 棄却ログ Audit
   ③ ──ApprovedFlowHandedOff (PL)──▶ loop-e2e（テスト作成・実行へ委譲）
```

因果整合: `ApprovedFlowHandedOff` は `BusinessFlowApproved` の後でのみ発火。`RejectedUsecaseRescued` は `UsecaseRejected` ＋ `ActualScenarioIngested` の両方を前提（救済フロー＝未配線）。

---

## Event Sourcing 対象

| Aggregate | ES | 理由 |
|-----------|----|----|
| **業務フロー（BusinessFlow）** | ✅ **採用** | PdM の承認/差し戻し履歴は再生成不可・一度きり。監査価値あり。状態＝イベント再生 |
| UseCase / Entity / 解析セッション | ❌ 不採用 | 対象コードから決定的に再生成可能（`enrich` が象徴）。状態上書きで十分 |
| Projection 各種（システム境界/情報モデル/…） | ❌ 不採用 | 確定層から再生成可能・確度 derived |
| 棄却ログ / 矛盾 | △ append-only ログ | 追記専用だが full ES（CQRS/再生）は過剰。`rejection_log.json` / `conflict_report.json` で足りる |

> 全面 ES は採らない。業務フローだけ CQRS 的な履歴を持ち、他は「再生成 or 追記ログ」。

---

## 未解決の問い

- `occurredOn` の実体化: 現状イベントは関数実行に暗黙化。型駆動（Phase 10）でイベント型に `occurredOn` を持たせるか、引き続き暗黙にするか。
- 業務フロー ES の保存先（JSON ストリーム / SQLite 等）と再生ロジックの置き場（#5・Phase 9–11）。
- 救済フロー（`RejectedUsecaseRescued`）の発火条件と所有者（② ACL 内 か 棄却ログ集約か）（#1 follow-on / Phase 9）。
