# Workflows — ワークフロー設計

生成日: 2026-06-25
前提フェーズ: storming ✓ / aggregates ✓ / events ✓ / mapping ✓（glossary 未・末尾フィードバック参照）
方式: DMMF（型駆動・パイプライン）。コードは書かない＝型駆動の設計ドラフト。

## 実装対象ワークフロー一覧（優先度順）

| # | 名前 | Bounded Context | 優先度 | 状態 | 理由 |
|---|-----|---------------|-------|------|-----|
| 1 | **業務フロー承認ループ** | ③ 業務フロー協働 | 高 | 🔴 未実装（#5） | 唯一の未実装・ES 的・PdM 承認（再生成不可のドメイン価値） |
| — | 抽出パイプライン | ① 要求モデル抽出 | （済） | ✅ | 実装済み（#1/#2 含む）。詳細は後追い `--analyze` |
| — | 実績調停パイプライン | ② 実績調停 | （済） | ✅ | 実装済み（#4 含む・救済は未）。詳細は後追い `--analyze` |

本フェーズは **#1 業務フロー承認ループのみ** を詳細設計（ユーザー選択）。

---

## Workflow 1: 業務フロー承認ループ（③ 業務フロー協働 BC）

### 概要

- **発動契機**: 確定 UC 群（`UsecaseConfirmed` 済み）が揃った後、`flow propose` 操作で想定を起動。以降は PdM 操作（review/feedback/edit/approve/handoff）と System 再想定の往復。
- **最終出力**: `Result<BusinessFlowEvent, BusinessFlowError>`。成功の終端は `ApprovedFlowHandedOff`（loop-e2e へ PL 引き渡し）。
- **性質**: **長時間実行・人間 in-the-loop・複数セッションにまたがる**（= Saga）。状態は **Event Sourcing**（イベント列を `fold` して復元）。
- **失敗カテゴリ**: 状態機械違反（不正遷移）/ 権限違反（PdM 以外）/ 参照エラー（確定 UC 不在）/ 技術例外（ストア I/O・loop-e2e 不達）。

### ステージ（中間型 ＝ 状態）

状態機械なので **ステージ＝状態型**。DMMF「信頼水準が上がる」を状態遷移にマップし、**各状態型が許す操作だけを公開**して不正状態を表現不能にする。

```
ProposedFlow → ReviewingFlow ⇄ NeedsRevisionFlow → ApprovedFlow → HandedOffFlow
                    │                                   ▲
                    └──────────── approve ──────────────┘
```

| ステージ（状態型） | この型が保証すること | 公開操作（許す遷移） |
|------------------|--------------------|-------------------|
| `ProposedFlow` | System が確定 UC 群から想定済み。`uc_ids` は全て確定(confirmed)UC。未レビュー | review / edit |
| `ReviewingFlow` | PdM がレビュー着手済み | feedback / edit / **approve** |
| `NeedsRevisionFlow` | PdM が FB 済み。`feedback_history` に理由。System 再想定待ち | rePropose(System) / edit |
| `ApprovedFlow` | **PdM 承認済み**。`approver` 記録。引き渡し可能 | **handOff のみ** |
| `HandedOffFlow` | loop-e2e へ引き渡し済み（終端） | （なし） |

> **不正状態を表現不能に**: `handOff` は `ApprovedFlow` 型にしか生えない＝「未承認の引き渡し」がコンパイル時に不能。`approve` は `NeedsRevisionFlow` には生えない（先に edit/reProposeで Reviewing へ戻す）。

### ステップ（コマンド ＝ 関数）

各コマンドは `(現状態, 入力, 依存) → Result<Event, Error>`。状態は `fold(events)` で前段再構築。

#### Step 1: proposeFlow
- 入力: `uc_ids[]` / 出力: `Result<BusinessFlowProposed, ProposeError>`
- 責務: 確定 UC 群から業務フローを想定（入力ゲート）
- 依存: `LoadConfirmedUsecases`
- 副作用: read-only（UC 照会）＋末端で append
- エラー: `NoConfirmedUsecases` / `UnknownUsecase(ucId)` / 指定 UC が confirmed でない
- 発行 Event: `BusinessFlowProposed`

#### Step 2: reviewFlow
- 入力: `ProposedFlow, by` / 出力: `Result<BusinessFlowReviewed, TransitionError|AuthError>`
- 責務: PdM レビュー着手 / 依存: なし / 副作用: none（＋append）
- 発行 Event: `BusinessFlowReviewed`

#### Step 3: giveFeedback
- 入力: `ReviewingFlow, feedback, actor` / 出力: `Result<BusinessFlowFeedbackGiven, AuthError>`
- 責務: 差し戻し理由を記録 → NeedsRevision へ / guard: **actor=PdM**
- 発行 Event: `BusinessFlowFeedbackGiven`（Enrichment: feedback 同梱）

#### Step 4: reProposeFlow
- 入力: `NeedsRevisionFlow, 依存` / 出力: `Result<BusinessFlowReProposed, ProposeError>`
- 責務: System が FB を反映して再想定（自動）/ 依存: `LoadConfirmedUsecases`
- 発行 Event: `BusinessFlowReProposed`

#### Step 5: editFlow
- 入力: `ProposedFlow|ReviewingFlow|NeedsRevisionFlow, edits, actor` / 出力: `Result<BusinessFlowEdited, AuthError>`
- 責務: PdM 手動微調整 / guard: **actor=PdM**
- 発行 Event: `BusinessFlowEdited`

#### Step 6: approveFlow 🎯
- 入力: `ReviewingFlow, actor` / 出力: `Result<BusinessFlowApproved, AuthError|TransitionError>`
- 責務: PdM 承認＝業務フロー確定 / **guard: actor=PdM（不変条件）・状態が Reviewing**
- 副作用: none（＋append）/ 発行 Event: `BusinessFlowApproved`（approver 記録）

#### Step 7: handOff 🎯
- 入力: `ApprovedFlow, 依存` / 出力: `Result<ApprovedFlowHandedOff, HandOffError>`
- 責務: 承認済みフローを loop-e2e へ引き渡し（出力ゲート）/ **guard: 状態が Approved（因果整合）**
- 依存: `HandOffToLoopE2e`（PL 送信）/ 副作用: **send-message（loop-e2e）**
- 発行 Event: `ApprovedFlowHandedOff`

### 依存（ポート一覧）

依存は**関数引数で渡す**（DMMF・DI コンテナを仮定しない）。

| 名前 | 型シグネチャ | 実装元 | 同期性 | 使うステップ |
|-----|------------|-------|-------|-----------|
| `LoadConfirmedUsecases` | `() → list[Usecase]` | ① Shared Kernel（`analysis_result.json`） | sync（file） | proposeFlow / reProposeFlow |
| `LoadFlowEvents` | `FlowId → list[BusinessFlowEvent]` | workflow store（JSONL） | sync | 全ステップ（fold 前段） |
| `AppendFlowEvent` | `(FlowId, BusinessFlowEvent) → unit` | workflow store（append-only） | sync | 全ステップ（末端） |
| `HandOffToLoopE2e` | `ApprovedFlow → Result<unit, HandOffError>` | loop-e2e（PL outbound） | async | handOff |
| `Now` | `() → Timestamp` | clock | — | 全ステップ（occurredOn） |

> `LoadConfirmedUsecases` は ② 救済フロー等と共通化候補（① Shared Kernel reader）。`LoadFlowEvents`/`AppendFlowEvent` が ES の心臓。

### エラーカタログ

```
BusinessFlowError =
  | Propose      of ProposeError
  | Transition   of TransitionError
  | Auth         of AuthError
  | HandOff      of HandOffError

ProposeError =
  | NoConfirmedUsecases
  | UnknownUsecase   of ucId: str
  | UsecaseNotConfirmed of ucId: str

TransitionError =
  | IllegalTransition of from: Status, command: str   # 状態機械違反

AuthError =
  | NotPdM of actor: str                              # approve/feedback/edit は PdM のみ

HandOffError =
  | NotApproved        of Status                       # 承認前の引き渡し（型で原則排除・防御的に二重化）
  | LoopE2eUnavailable                                 # 技術例外寄り
```

ドメインエラー vs 技術例外の仕分け: `Propose/Transition/Auth` はドメインエラー（UI に出す）。`LoopE2eUnavailable` は技術例外（リトライ/ログ）。

UI 表示マッピング（Phase 11 / UI 項目への入力）:

| エラー | UI 反応 |
|-------|--------|
| `NotPdM` | 承認/FB/編集ボタンを非活性、「PdM のみ操作可能」 |
| `IllegalTransition` | 現状態で不可の操作ボタンを非活性 |
| `NoConfirmedUsecases` | 「確定 UC がありません。先に解析を確定してください」 |
| `LoopE2eUnavailable` | 「loop-e2e へ接続できません。時間を置いて再試行」 |

### 発行イベント

| ステップ | 発行 Event | 条件 | 購読側 |
|--------|-----------|-----|-------|
| approveFlow 成功 | `BusinessFlowApproved` | actor=PdM ＆ Reviewing | 自 BC（引き渡し前提） |
| handOff 成功 | `ApprovedFlowHandedOff` | Approved のみ | **loop-e2e（PL）** |
| 各コマンド成功 | 対応 Event | guard 通過時 | ES ストア（append → fold 対象） |

### 副作用の配置（I/O at the edges）

```
[store] → LoadFlowEvents(read) → fold(pure) → command guard(pure) → Result<Event>
                                                          │
                                        成功 → AppendFlowEvent(write) ┐
                                        handOff → HandOffToLoopE2e(send)┘ → [外界]
```

- **純粋**: `fold`（状態復元）・各コマンドの guard 判定・Event 組み立て。
- **副作用は両端のみ**: 先頭 `LoadFlowEvents`（read）、末端 `AppendFlowEvent`（write）/ `HandOffToLoopE2e`（send）。
- ES の `fold` が純粋なので、状態遷移ロジックはテストで I/O 不要（イベント列を渡すだけ）。

### 関係するワークフロー

- **上流**: 抽出パイプライン（① `UsecaseConfirmed` → 確定 UC 群が proposeFlow の入力）。Event/Shared Kernel 経由（直接呼び出しでない）。
- **下流**: loop-e2e（`ApprovedFlowHandedOff` → PL）。テスト作成・実行は委譲＝BC 境界を越えない。
- **Saga 性**: 長時間・人間 in-loop・複数セッション。補償は「フロー破棄/差し替え」（MVP 外）。

### 未解決の問い

- ES の保存先（`output/usecases/business_flows/<flowId>.jsonl` 想定）と `fold` の置き場（`workflow/` 新パッケージ＝#7 構成と一致）。
- `edit` が複数状態（Proposed/Reviewing/NeedsRevision）で起きる → 状態型ごとに `editFlow` を持たせるか、共通化するか（Phase 10 型設計）。
- 承認操作の UI（CLI 対話 / ④ ビューワー）— openQuestion 継続（Phase 11）。
- 補償（承認後に確定 UC が変わった場合のフロー無効化）は MVP 外 → 残課題。

---

## ワークフロー間の関係図

```
抽出パイプライン(①) --[UsecaseConfirmed / Shared Kernel]--> 業務フロー承認ループ(③)
業務フロー承認ループ(③) --[ApprovedFlowHandedOff / PL]--> loop-e2e(外部)
実績調停(②) --[Shared Kernel 書き戻し]--> 抽出パイプライン(①)
```

## 共通パターンの識別

- **ES fold は ③ 固有**（① ② は再生成 or 上書き）。`workflow/` に閉じる。
- **`LoadConfirmedUsecases`（① Shared Kernel reader）は ②救済 と共通化候補** → `shared/` 配置（#7）。
- **guard（状態機械・権限）は純粋関数**＝テスト先行しやすい（sync 実装時 TDD の起点）。

## フィードバック（元フェーズへの差し戻し提案）

| 発見 | 差し戻し先 | 内容 |
|-----|----------|-----|
| 中間型名 `ProposedFlow`/`ReviewingFlow`/`NeedsRevisionFlow`/`ApprovedFlow`/`HandedOffFlow` が用語集に無い | Phase 8 (glossary) | 状態型を正式用語として登録 |
| `Status`（proposed/reviewing/needs_revision/approved/handed_off）の値域 | Phase 10 (types) | Literal 型＋状態ごとの専用型で「不正状態を表現不能」に |
| `edit` の複数状態対応 | Phase 5 (aggregates) | BusinessFlow の操作粒度を再確認（状態ごとの edit か共通か） |
| `BusinessFlowError` 階層は events に未記載 | Phase 6 (events) | エラーは Event でなく Result。events.md は変更不要（確認のみ） |

→ 次は **Phase 10 (types)** で上記ステージ型・`Result`・`Status`・エラー階層を「コンパイル可能・不正状態を表現不能」な型へ落とすのが自然。その後 **sync** で `workflow/` を TDD 実装（`fold` の純粋性・guard の不変条件をテスト先行）。
