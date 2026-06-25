# Bounded Contexts

> Phase 3 / DDD — rdra-analyzer 自身のドメイン。[discovery.md](discovery.md) / [event-storming.md](event-storming.md) を踏まえる。

## Context Map 概要図

```
                          ┌──────────────────────────────────────────────┐
                          │ ① 要求モデル抽出コンテキスト        ★Core      │
                          │                                              │
   [対象リポジトリ] ─────▶│  [確定層] UC・エンティティ                     │
   (ソースコード)         │          コード証拠で確定（高確度）            │
                          │            │ 確定物を入力に                   │
                          │  [派生層] 情報モデル/状態遷移/BP/              │
                          │          システム境界/CRUDギャップ            │
                          │          合成・推論（確度ラベル付き）          │
                          └───┬──────────────┬───────────────┬───────────┘
                              │確定UC/エンティティ            │確定物
            実績で救済/矛盾検出│              │確定UC          ▼
                              ▼              ▼        ┌──────────────────┐
   [loop-e2e]──実績──▶┌──────────────┐ ┌──────────────┐│ ④ 可視化          │
   (外部システム)      │ ② 実績調停    │ │ ③ 業務フロー  ││   Supporting      │
                      │   Supporting  │ │   協働        ││  Mermaid/viewer   │
                      │   (ACL)       │ │   Supporting  │└──────────────────┘
                      │ 「コードを真」 │ │ PdM承認ループ │
                      └──────────────┘ └──────┬───────┘
                                              │承認済み業務フロー
                                              ▼
                                         [loop-e2e へ引き渡し]
```

## Bounded Context 一覧

### ① 要求モデル抽出コンテキスト (Core)

- **責務**: 対象コードから RDRA 要求モデルを **コード証拠ベースで正確に起こす**。Core Domain。
- **内部2層**:
  - **確定層** — ユースケース・エンティティ。コード証拠と一対一で確定（高確度・確度ラベル不要）。最小コア抽出物。
  - **派生層** — 情報モデル（リレーション）／状態遷移／ビジネスポリシー／システム境界／CRUDギャップ。確定層を入力に合成・推論（**確度ラベル必須**）。
- **不変条件**: 両層とも「抽出要素 → コード証拠」の対応が必須。根拠なきものは確定モデルに出さず棄却（→ 棄却ログ）。
- **主要概念**: APIエンドポイント, エンティティ, ユースケース, 棄却ログ, 情報モデル, 状態遷移, ビジネスポリシー, システム境界, CRUDギャップ, 解析セッション
- **ユビキタス言語**: 抽出 / 照合 / 証拠 / 確定（＝コード証拠で裏付け）/ 棄却 / 確度ラベル / 確定層 / 派生層 / 接点（画面）/ 起点（エンドポイント）
- **所有チーム**: TBD

### ② 実績調停コンテキスト (Supporting / ACL)

- **責務**: loop-e2e の実績シナリオを取り込み、要求モデルへ突き合わせる。外部システムとの境界（腐敗防止層）。
- **調停ルール**（[discovery.md](discovery.md) のコア判断基準）:
  - 静的で確定 → そのまま確定
  - 静的で棄却 ＋ 実績あり → **救済**（「実績由来」確定）
  - 静的に無い ＋ 実績のみ → 新規UC（`UC-LE-NNN`）
  - 静的で確定 ＋ 実績と矛盾 → **コードを真**・要調査フラグ
- **主要概念**: 実績シナリオ, 救済, 矛盾検出, 要調査フラグ, **矛盾（`Conflict` 型・sync #4 で実装）**
- **ユビキタス言語**: 実績 / 救済 / 矛盾 / 調停 / 実績由来。**「確定」は抽出 BC と意味が連続するが、出自が「コード」でなく「実績」である点が異なる**
- **所有チーム**: TBD

### ③ 業務フロー協働コンテキスト (Supporting)

- **責務**: 確定 UC 群から業務フローを想定し、PdM の承認を経て確定。承認済みを loop-e2e へ引き渡す。
- **承認ループ**: 想定（自動）→ レビュー（PdM）→ FB（PdM）→ 再想定（自動）→ 微調整（PdM 手動）→ 承認（PdM）
- **責務の境界**: 生成＋PdM 承認まで。**テスト作成・E2E 実行は loop-e2e（スコープ外）**。
- **主要概念**: 業務フロー, 承認, フィードバック, 引き渡し
- **ユビキタス言語**: 業務フロー / 想定 / レビュー / 承認（＝**PdM が確定**）/ 微調整 / 引き渡し
- **所有チーム**: TBD

### ④ 可視化コンテキスト (Supporting)

- **責務**: 抽出・合成された RDRA モデルを Mermaid 図・インタラクティブビューワーで PdM に見せる。説明の器。
- **主要概念**: Mermaid 図, ビューワー, クロスリファレンス, コード参照箇所
- **ユビキタス言語**: ER図 / 複合図 / パネル / ズーム・パン / クロスリファレンス
- **所有チーム**: TBD

### Generic Subdomains

- **LLM プロバイダ抽象** (Generic): Anthropic API / Claude Code CLI。代替可能な汎用基盤。
- **プロジェクトコンテキスト構築** (Generic): CLAUDE.md/AGENTS.md/マニフェスト読込。汎用前処理。

## サブドメイン分類まとめ

| Bounded Context | サブドメイン種別 | 1 BC = 1 Subdomain |
|----------------|----------------|--------------------|
| 要求モデル抽出 | **Core** | ✅（確定層＋派生層を1つの Core に統合） |
| 実績調停 | Supporting (ACL) | ✅ |
| 業務フロー協働 | Supporting | ✅ |
| 可視化 | Supporting | ✅ |
| LLM プロバイダ抽象 | Generic | ✅ |
| プロジェクトコンテキスト構築 | Generic | ✅ |

## 言語の境界で発見した事実

- **「確定」**は文脈で確定者が変わる：抽出 BC ＝ **コード証拠**で裏付け（自動・System）／業務フロー協働 BC ＝ **PdM が承認**（人間）。→ 別コンテキスト。
- **「検証」**：抽出 BC ＝「コード証拠と照合」／loop-e2e 側＝「E2E 実行検証」（スコープ外）。境界の外と明確に区別する。
- **「ユースケース」**：抽出 BC ＝コード由来の検証済み UC／実績調停 BC ＝実績由来 UC（`UC-LE`、コードに無い）。出自が異なる。

## コードベース突き合わせ（`--analyze`）

> このモデルは **as-built（現状）ではなく to-be（目標）**。Core の柱の一部はまだコードに無い＝これから作る差別化。
> Precision/棄却ログは **目標として維持**（コードを今後作り変える北極星）。

### 各 BC の実装状況

| BC | 設計要素 | コード現状 | 状態 |
|----|---------|-----------|------|
| ① 要求モデル抽出 | コード証拠/トレーサビリティ | `EntityOperation.call_chain`, `*_evidence`, `code_references`, `Usecase.related_*` | ✅ 実装済み |
| ① 確定層 | **Precision 棄却 ＋ 棄却ログ** | `rejection_log.py`：コード証拠なき UC を `partition_usecases` で棄却し `rejection_log.json` へ（独立 `RejectedUsecase` 型）。`analyze --strict` で opt-in（既定は現行 Recall 維持）。救済フローは未配線 | ✅ 実装済み（opt-in, sync #1）/ 🟡 救済は残 |
| ① 派生層 | **確度ラベル** | `confidence` 三値（confirmed/derived/inferred）を `Usecase`/`EntityOperation` に導入。合成UCは inferred、静的抽出は confirmed。派生図への付与は可視化として後続 | ✅ 実装済み（sync #2） |
| ① 派生層 | 情報モデル/状態遷移/BP/CRUDギャップ | 各ジェネレータ実装済み | ✅ 実装済み |
| ① 派生層 | **システム境界の生成** | `rdra/system_boundary.py`：接点（画面）× 起点（エンドポイント）を決定的に Mermaid 出力（`rdra/system_boundary.md`）。LLM 不要＝確度 derived | ✅ 実装済み（sync #3） |
| ② 実績調停 | 「コードを真」の調停 | `reconcile.py`: route match → checkpoint 事実確認 → synthesize。コードが勝つ | ✅ 実装済み（部分） |
| ② 実績調停 | **矛盾検出 ＋ 要調査フラグ** | `conflict_report.py`＋`detect_conflicts`：マッチ UC と実績の actor/controller 不一致を `conflict_report.json` へ（コードを真・UC 不変） | ✅ 実装済み（sync #4） |
| ③ 業務フロー協働 | **PdM 承認ループ** | 丸ごと未実装。`activity_diagram.py` は 100% 自動生成、承認ゲートなし | 🔴 未実装（目標） |
| ④ 可視化 | Mermaid / ビューワー | `viewer_template.py`, `mermaid_renderer.py` | ✅ 実装済み |

### BC ↔ コードモジュール対応（sync 後 / contexts --analyze）

> 6 BC はすべてコードに存在し概念構造は健全。ただし**パッケージは技術レイヤで切られ BC を横断**する。

| BC | コードモジュール |
|----|-----------------|
| ① 確定層 | `analyzer/`: `usecase_extractor`・`source_parser`・`screen_analyzer` |
| ① 派生層 | `rdra/`: `information_model`・`state_transition`・`business_policy`・`crud_matrix`・`system_boundary`(#3) ＋ `gap/crud_analyzer` |
| ① Precision/棄却 | `analyzer/rejection_log`(#1) |
| ① 確度（横断 kernel） | `confidence.py`（top-level, #2） |
| ② 実績調停（ACL） | `analyzer/`: `reconcile`・`conflict_report`(#4)・`scenario_builder`(共有型) |
| ③ 業務フロー協働 | `rdra/activity_diagram`（一方向のみ・承認ループ無し） |
| ④ 可視化 | `rdra/`: `mermaid_renderer`・`viewer_template`・`usecase_diagram` |
| LLM 抽象（Generic） | `llm/` |
| プロジェクトコンテキスト構築（Generic） | `analyzer/project_context`・`knowledge/loader` |

**🔴 構造ズレ（#7 を定量化）**: `analyzer/` が **3 BC**（①確定層・②実績調停・Generic）にまたがり、`rdra/` も **3 BC**（①派生層・③業務フロー・④可視化）にまたがる。`gap/` は ①派生層の生成器1個だけが孤立。sync 新規モジュールも技術レイヤ慣習に従い #7 を強化したが、`confidence.py`（top-level 共有 kernel）と `conflict_report`→`analyzer/`（②に正しく同居）は妥当配置。**`scenario_builder` の `OperationScenario` 型は ①/②/④ が横断利用＝`confidence` と並ぶ Shared Kernel 候補**。

### 設計が切ったのにコードに残るもの（要撤去・整理）

- ~~`scenarios` / `verify` / `e2e` コマンドが main.py に残存~~ → ✅ **sync #6 で撤去**（コマンド＋`scenario_verifier`/`e2e/`/playwright を削除、`all` を再配線）。`scenario_builder` は analyze/rdra/gap/reconcile が依存する共有型のため存置。
- コード実体の継ぎ目は **Source / UseCase / Scenario / Reconciliation** の4分割で、設計の継ぎ目とズレている。→ 🟡 Scenario context は `scenario_builder` 型のみへ縮小（#6）。残る 4 BC への横断リファクタ（#7）は **Phase 4 mapping の関係種別確定が前提**で deferred。BC 整合の目標構成: `extraction/`・`reconciliation/`・`workflow/`・`visualization/`・`shared/`（confidence+scenario_builder）・`llm/`・`context/`。

### `--analyze` から導かれる作業の北極星（sync 進捗）

1. ✅ **棄却ログ ＋ Precision 棄却**（sync #1, opt-in `--strict`）
2. ✅ 派生層への**確度ラベル**（sync #2, 三値）
3. 🔴 **業務フロー協働 BC**（PdM 承認ループ）— sync #5 deferred（Phase 5/9–11 が前提）
4. ✅ **システム境界**（sync #3）・**矛盾検出/要調査フラグ**（sync #4）
5. ✅ スコープ外（scenarios/verify/e2e）の撤去（sync #6）

## 未解決の問い

- ~~「棄却ログ」は独立 Aggregate か、ユースケースの状態（rejected）か~~ → ✅ sync #1 で**独立型 `RejectedUsecase`** に確定（Phase 5 で Aggregate 化を最終判断）。
- システム境界 Aggregate と画面・エンドポイントの所有関係（Phase 5）。
- ~~BC 間の関係種別（Partnership / Customer-Supplier / ACL / Published Language 等）の確定。特に loop-e2e との上流/下流関係~~ → ✅ **Phase 4 mapping で確定**（[context-map.md](context-map.md)）。loop-e2e は双方向別契約（②へ実績 PL／③から承認済みフロー PL）、①⇔②は Shared Kernel。
- ~~確度ラベルの値域~~ → ✅ sync #2 で**三値（confirmed/derived/inferred）**に確定。
- 新概念 `Conflict`（sync #4）を独立 Aggregate 化するか（Phase 5）。
