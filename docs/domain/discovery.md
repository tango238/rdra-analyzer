# Discovery

> Phase 1 / DDD — Core Domain の特定（rdra-analyzer 自身のドメイン）

## ビジネス概要

`rdra-analyzer` は、既存リポジトリのソースコードを **RDRA（Relationship-Driven Requirements Analysis）の要求モデル**へ翻訳し直すツール。
主要ユーザーは **PdM（プロダクトマネージャー）**。PdM が次の3つの問いに答えられるよう、コードを「要求の言葉」で読み解けるようにする。

1. このコードは本当に必要か？（必要性の検証）
2. なぜ必要なのか？（存在理由・根拠の説明）
3. 次に作るなら何か？（次機能の示唆）

判断そのものは PdM が下す。ツールの役割は、判断に足る **正確な要求モデルを供給する**こと。

## Core Domain

- **名前**: RDRA 要求モデル抽出（Requirements Model Extraction）
- **責務**: 言語・フレームワーク非依存で、LLM 駆動で対象コードを動的解析し、
  情報モデル・ユースケース・状態遷移・ビジネスポリシーといった **RDRA モデルをコードと乖離なく起こす**。
- **理由（なぜ Core か）**: PdM の3つの問いに答える土台はすべてここ。抽出が正確でコードと一致していれば、
  判断は PdM 側で可能。逆に抽出が不正確・コード乖離していれば、上に乗る一切の分析・可視化が信頼を失う。
- **差別化要因**:
  - **言語・FW 非依存**（Laravel/Rails/Django/Spring/Go/Rust… を `CLAUDE.md`/`AGENTS.md` コンテキストで横断）
  - **コードとの乖離防止**（`enrich` による checkpoint からの決定的な再導出＝LLM に依存しない事実ベースの紐付け）
  - 図やビューワーは「説明の器」にすぎず、競争優位は抽出の正確さに宿る。

## 分析インプット（2系統）

| 系統 | 源泉 | 意味 |
|------|------|------|
| **静的** | 対象リポジトリのソースコード | コードに刻まれた「あるべき要求」 |
| **動的（取り込み）** | loop-e2e のシナリオ実績（`reconcile`） | 「実際に使われている要求」の裏付け。要求モデルへ突き合わせる |

## Core の品質基準と調停ルール（深掘りで確定）

### 品質の最優先軸：正確性（Precision）

「乖離なく」の中で **(b) 正確性 = 幻覚を出さないこと** が最優先。
PdM は「このUCは実在する」前提で必要性を語るため、コードに無いものを抽出するのが最も致命的。
取りこぼし（網羅性）より、嘘を出さないことを優先する。

### Core の不変条件（invariant）

- **抽出要素 → コード証拠** の対応が常に存在する。**根拠なき UC・エンティティは確定モデルに出さない。**
- 方針は **(P) Precision 重視＝棄却**。裏付けの取れない抽出は確定モデルから捨てる。
- ただし **棄却＝破棄ではない**。Core は2つのアウトプットを持つ：
  1. **確定要求モデル** — 根拠あり。PdM が判断に使う。
  2. **取りこぼし・棄却ログ** — 根拠を示せず棄却したものを記録し、**検証フロー**へ回す（取りこぼしの見える化）。

### 静的抽出 ↔ loop-e2e 実績（動的）の調停ルール

| 状況 | 調停 |
|------|------|
| 静的で確定 | そのまま確定（コード根拠が最強） |
| 静的で棄却 ＋ loop-e2e に実績あり | **救済**して「実績由来」ラベルで確定（実際に動いている証拠） |
| 静的に無い ＋ loop-e2e のみに在る | 新規UC（`UC-LE-NNN`）として取り込み（既存 `reconcile` 挙動） |
| **静的で確定 ＋ loop-e2e と矛盾** | **コードを真とする**（システムのコア判断基準）。矛盾は「要調査」フラグで記録し PdM に提示（実装と実挙動のズレ＝バグ or 仕様変更の兆候） |

> **コア判断基準**: 矛盾時はコードを真とする。

## Supporting Subdomains

- **ソースコード解析**（`source_parser` / `screen_analyzer` / `project_context`）: コードからルート・モデル・画面を抽出し Core に供給する。Core に必須だが差別化ではない。
- **CRUD ギャップ分析**（`gap`）: 抽出済みモデルから孤立エンティティ・欠落操作を導く派生分析。PdM の「本当に必要か」を補助する。
- **可視化 / ビューワー**（`mermaid_renderer` / `viewer_template`）: 抽出結果を PdM に伝える説明の器。
- **外部実績データ取り込み**（`reconcile` / `enrich`）: loop-e2e のシナリオを分析対象データとして取り込み、要求モデルを補強する。

## Generic Subdomains

- **LLM プロバイダ抽象**（`llm/` — Anthropic API / Claude Code CLI）: 代替可能な汎用基盤。
- **Mermaid 記法レンダリング**: 既存記法への変換。汎用。

## スコープ外（今回のドメインモデルに含めない）

- **E2E 実行**: 別システム（loop-e2e）へ委譲済み。
- **操作シナリオ生成（`scenarios`）**: 不要。loop-e2e へ一本化。

## ビューワー切り出し方針（`@rdra/viewer`）— 本セッションで確定

Core（RDRA要求モデル抽出）の責務は **正確な解析まで**。可視化/ビューワーは Supporting Subdomain
として **独立した npm パッケージ CLI `@rdra/viewer`** に切り出す。

### 位置づけ
- Viewer = **Supporting Subdomain**（rdra 出力専用ビューワーを別 npm へ分離するのみ）。
  汎用ビューワー化（Generic 路線・公開仕様化）は **採らない**。契約は内部仕様で可。

### 境界＝表示契約 / 集計・レイアウトは現状維持（"いままで通り"）
- 境界は **完成形の view-model JSON（`rdra-view-model.json`）**。
- Core 側の再導出ロジック（`_build_viewer` 内の `_enrich_*` / `InformationModelGenerator` /
  `business_policies.md`・`state_transitions.md` のパース / mermaid ソース構築）は **動かさない**。
- クライアント側レイアウトJS（`viewer_template.py` の描画ロジック）も **変更しない**（移植のみ）。
- 唯一の新規要素は「組み立て済み `DATA` をファイルへ直列化する」工程だけ。

> 注意（現状の結合）: 現 `_build_viewer`（main.py:1232〜）は表示生成なのに Core の再導出を内包している。
> 切り出しでは「DATAを組み立てる責務」は Core 側に残し、その**出力（DATA）を JSON 化した時点を境界**とする。
> npm 側は解析・再導出を一切持たない dumb renderer。

### アーキテクチャ

```
[Core: rdra-analyzer (Python)]   ← 解析・集計は現状のまま
   accurate RDRA analysis → DATA を組み立て
        ↓  emit rdra-view-model.json  （契約 = 現行 DATA 形状 + mermaid_sources）
[Supporting: @rdra/viewer (npm CLI)]   ← npx rdra-viewer ./rdra-view-model.json
   現行 HTML テンプレ + クライアントJS を移植し、JSON 注入 → Node 静的サーバで配信
```

### 表示契約スキーマ（`visualization/mermaid_renderer.py::_render_viewer` の現行 `DATA` をそのまま採用）

`entities` / `relationships` / `usecases` / `scenarios` / `state_machines` / `policies` /
`information_groups` / `screen_specs` / `entity_operations` / `uc_entity_crud` /
`mermaid_sources` / `generated_at`。

→ Core はこの JSON を吐くだけ、npm 側はこの JSON だけを入力に描画。両者とも現行ロジック不変。

## SWOT（任意・暫定）

| Strengths | Weaknesses |
|-----------|-----------|
| 言語・FW 非依存の横断抽出 / コード乖離防止の決定的紐付け（enrich） | LLM 抽出の精度・再現性に品質が依存 / コード規約が薄いリポジトリでは精度低下 |

| Opportunities | Threats |
|-------------|---------|
| loop-e2e 実績との突き合わせで「生きた要求」を可視化 / PdM 向け判断支援アウトプットの拡張余地 | 対象コードの規模・多様性増大に伴う抽出コスト / LLM 出力の非決定性 |

## 未解決の問い

- RDRA モデルの構成要素（情報モデル / UC / 状態遷移 / ビジネスポリシー）のうち、どれが抽出の最小コアで、どれが派生か — Phase 2/3 で境界を引く際に要確定。
- `@rdra/viewer` 切り出しの実装上の問い:
  - 契約 `rdra-view-model.json` を**正式スキーマ（JSON Schema/型）として固定**するか、当面は内部仕様の暗黙契約で進めるか。
  - Core 側で JSON を吐く工程をどのコマンドに載せるか（`viewer --export-only` / `rdra` の追加出力 / 新規 `export` コマンド）。
  - npm パッケージ配布形態（npm 公開 or 社内/ローカル `npx` 運用）。
  - mermaid を実行時CDN取得にするか npm 同梱（オフライン）にするか。

### 深掘りで解決済み

- ~~「コードと乖離なく」をどう保証・検証するか~~ → **正確性(Precision)最優先・根拠なきものは棄却・棄却ログ＋検証フローで見える化**（上記「Core の品質基準」参照）。
- ~~loop-e2e 実績と静的抽出が食い違ったときどちらを真とするか~~ → **矛盾時はコードを真**（上記「調停ルール」参照）。
