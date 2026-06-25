# ユビキタス言語（用語集）

> Phase 8 / DDD — 全フェーズで蓄積した用語を BC ごとに整理。英名は Phase 10 型／コード実体と対応。
> 同一用語が文脈で意味を変えるもの（確定／検証／ユースケース）は「横断の注意点」に記録。

## Core 横断（確度・証拠）

| 用語 | 英語 / コード | 定義 |
|------|------|------|
| 確度ラベル | `Confidence`（`confidence.py`） | 抽出物の根拠の強さ。三値 `confirmed`/`derived`/`inferred`（sync #2） |
| 確定 | confirmed | コード証拠と 1:1 で裏付く確定層。確定者は文脈依存（→横断注意点） |
| 派生 | derived | 確定層から決定的に導出した派生層（確度ラベル必須） |
| 推論 | inferred | LLM 推論・reconcile 合成など弱い根拠 |
| 証拠アンカー | evidence anchor | UC をコードに接地する `related_routes`/`_controllers`/`_entities`/`_pages` |
| 証拠の連鎖 | evidence chain | APIエンドポイント→Controller→モデル＋画面→UC候補 |

## BC ① 要求モデル抽出（Core）

| 用語 | 英語 / コード | 定義 |
|------|------|------|
| ユースケース | `UseCase`（`Usecase`） | コード証拠で確定した要求単位。確定層。確度付き |
| エンティティ | `Entity`（`ParsedModel`＋`EntityOperation`） | 操作対象の概念。CRUD 操作を持つ |
| APIエンドポイント | `ApiEndpoint`（`ParsedRoute`） | 起点。method＋path（VO） |
| 画面 | `Screen`（`ParsedPage`） | 接点。route_path＋component（VO） |
| 解析セッション | `AnalysisSession`（checkpoint） | 解析の進行（parse→done）を束ねる Process |
| 棄却 | rejection | コード証拠なき UC を確定モデルから外すこと（Precision・sync #1） |
| 棄却ログ | `RejectedUsecase`（`rejection_log.py`） | 棄却の追記専用記録（理由＋欠落証拠）。破棄でなく検証フローの入力 |
| 接点 | contact point | アクターがシステムに触れる点＝画面 |
| 起点 | entry point | システムの入口＝APIエンドポイント |
| システム境界 | `SystemBoundary`（`system_boundary.py`） | 接点×起点の対応の Projection（集約でない・確度 derived・sync #3） |
| 再導出（enrich） | enrich | checkpoint から related_* を決定的に埋め直す（LLM 不要） |
| 情報モデル/状態遷移/ビジネスポリシー/CRUDギャップ | Projection（`rdra/`,`gap/`） | 確定層から導出する派生投影（Read Model・確度 derived） |

## BC ② 実績調停（Supporting / ACL）

| 用語 | 英語 / コード | 定義 |
|------|------|------|
| 実績シナリオ | `OperationScenario`（`scenario_builder`） | loop-e2e の実行実績。ACL で取り込む |
| 調停 | reconcile（`reconcile.py`） | 静的抽出と実績を突き合わせる |
| 救済 | rescue | 静的棄却 UC を実績で「実績由来」確定に再昇格（未配線・残課題） |
| 矛盾 | `Conflict`（`conflict_report.py`） | マッチ UC と実績の食い違い（actor/controller）。追記専用 Audit（sync #4） |
| 要調査フラグ | needs-investigation | 矛盾を PdM 提示用に記録。UC は変更しない |
| コードを真 | code-wins | 矛盾時は静的（コード）を正とするコア判断基準 |

## BC ③ 業務フロー協働（Supporting）

| 用語 | 英語 / コード | 定義 |
|------|------|------|
| 業務フロー | `BusinessFlow`（`workflow/`） | 確定 UC 群から想定し PdM が承認する業務の流れ。ES（sync #5） |
| 想定中 | `ProposedFlow` | System が想定済み・未レビューの状態 |
| レビュー中 | `ReviewingFlow` | PdM がレビュー着手済みの状態 |
| 要修正 | `NeedsRevisionFlow` | PdM が差し戻した状態（feedback 記録） |
| 承認済み | `ApprovedFlow` | PdM 承認済み。引き渡し可能 |
| 引き渡し済み | `HandedOffFlow` | loop-e2e へ引き渡した終端状態 |
| 想定する | propose | 確定 UC 群から業務フローを起こす（System） |
| レビューする | review | PdM がレビューに着手 |
| フィードバック | feedback | PdM が差し戻す（→要修正） |
| 再想定 | re-propose | System が FB を反映し作り直す |
| 編集 | edit | PdM が手動微調整 |
| 承認 | approve | PdM が確定（＝業務フロー確定。**PdM のみ**） |
| 引き渡し | handoff | 承認済みを loop-e2e へ（PL 成果物 `*.handoff.json`） |

## BC ④ 可視化（Supporting）

| 用語 | 英語 / コード | 定義 |
|------|------|------|
| Mermaid 図 | mermaid（`mermaid_renderer.py`） | RDRA モデルの図表現 |
| ビューワー | viewer（`viewer_template.py`） | インタラクティブ閲覧 UI |
| クロスリファレンス | cross-reference | 図要素とコード参照箇所の相互リンク |

## Generic Subdomains

| 用語 | 英語 / コード | 定義 |
|------|------|------|
| LLM プロバイダ | `LLMProvider`（`llm/`） | Anthropic API / Claude Code CLI の抽象。代替可能 |
| プロジェクトコンテキスト | `ProjectContext`（`project_context.py`） | CLAUDE.md/AGENTS.md/マニフェスト読込 |

## アクター

| 用語 | 定義 |
|------|------|
| PdM | プロダクトマネージャー。判断と業務フロー承認の確定者 |
| System | rdra-analyzer。抽出・照合・確定/棄却・合成の自動実行者 |
| loop-e2e | 外部システム。実績の供給元（②へ）／承認済みフローの引き渡し先（③から） |

## コンテキスト横断の注意点（多義語）

| 用語 | ① 要求モデル抽出 | 他コンテキスト |
|------|----------------|----------------|
| **確定** | コード証拠による自動確定（System） | ③：PdM 承認による人間確定 |
| **検証** | コード証拠と照合 | loop-e2e：E2E 実行検証（スコープ外） |
| **ユースケース** | コード由来の検証済み UC | ②：実績由来 UC（`UC-LE`・コードに無い） |
| **確定（②の救済）** | — | ②：出自が「コード」でなく「実績」の確定 |

## コードとの対応（--analyze 観点）

| 用語集 | コード上の名前 | 整合 |
|--------|-------------|------|
| 確度ラベル | `Confidence` / `confidence` | ✅ |
| 棄却ログ | `RejectedUsecase` / `rejection_log.py` | ✅ |
| 矛盾 | `Conflict` / `conflict_report.py` | ✅ |
| 業務フロー（状態） | `ProposedFlow`/`ReviewingFlow`/`NeedsRevisionFlow`/`ApprovedFlow`/`HandedOffFlow` | ✅（sync #5 で登録・workflows.md フィードバック解消） |
| ユースケース | `Usecase`（小文字 c） | 🟡 軽微な綴り（`Usecase` vs `UseCase`）。コード現状を許容 |
| システム境界 | `SystemBoundaryGenerator` | ✅（Projection＝生成器のみ） |

## 未解決の問い

- `Usecase` vs `UseCase` の綴り統一（コード広範のため #7 リファクタ時に検討）。
- 救済（rescue）の正式英名と配線（#1 follow-on）。
