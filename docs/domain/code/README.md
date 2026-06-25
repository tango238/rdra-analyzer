# Code ↔ Domain Model Mapping（Phase 10: types）

> `docs/domain/*.md` から翻訳した **型定義のみ**（DMMF「型を先に、実装は後で」）。関数本体は書かない。
> **言語**: 本プロジェクトに合わせ **Python**（既定の TypeScript ではない）。これらの型は sync で
> `workflow/` パッケージ（#5 実装）へ持ち上げる骨格になる。
> 対象は Phase 9 で選択した **業務フロー承認ループ（③ / #5）** のみ。

## 対応表

| コード | 由来 | セクション |
|------|-----|----------|
| `util/result.py` の `Result/Ok/Err` | DMMF 基盤 | — |
| `types/value_objects.py` の `FlowId/UsecaseId/Timestamp/Actor/Status` | aggregates.md / workflows.md | VO・Status 値域 |
| `types/states.py` の `ProposedFlow/ReviewingFlow/NeedsRevisionFlow/ApprovedFlow/HandedOffFlow` | workflows.md | ステージ（状態型） |
| `types/events.py` の 7 イベント | domain-events.md | BC ③ イベント |
| `types/errors.py` の `BusinessFlowError` 階層 | workflows.md | エラーカタログ |
| `types/ports.py` の依存（`LoadConfirmedUsecases` 等） | workflows.md | 依存ポート一覧 |
| `types/workflow.py` の `Fold` / 各コマンド型 | workflows.md | ステップ |

## 「不正状態を表現不能に」の要点

- `HandOff` は `ApprovedFlow` しか受け取らない → 未承認の引き渡しが型レベルで不能。
- `ApproveFlow` は `ReviewingFlow` のみ → 提案直後/差し戻し中の直接承認を排除。
- `Status`/`Actor` は `Literal`、識別子は `NewType` ブランド → 生 str との取り違え防止。
- エラーは `Result<_, BusinessFlowError>`（例外でなく値）。

## 型チェック

- `python -m py_compile` で構文検証済み。
- 完全な型チェック（`mypy --strict`）はローカル未導入のため CI 委譲。

## 未翻訳の要素 / 差し戻し

- 中間型名（`ProposedFlow` 等）は **glossary 未登録** → Phase 8（glossary）で正式化。
- `LoadConfirmedUsecases` の戻り型は設計上 `Sequence[UsecaseId]`。実装は full `Usecase` を返す（① Shared Kernel reader）→ sync で確定。
- 抽出①/調停② のワークフロー型は対象外（実装済み・後追い `--analyze`）。
