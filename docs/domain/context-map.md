# Context Map

> Phase 4 / DDD — rdra-analyzer の Bounded Context 間関係。[bounded-contexts.md](bounded-contexts.md) の 6 BC ＋ 外部 loop-e2e。
> openQuestion「BC 間の関係種別（特に loop-e2e との上流/下流）」を解消する。

## 図

```mermaid
flowchart LR
    subgraph ext["外部システム"]
        LE["loop-e2e"]
    end

    PC["プロジェクトコンテキスト構築<br/>(Generic)"]
    LLM["LLM 抽象<br/>(Generic)"]
    CORE["① 要求モデル抽出<br/>★Core"]
    REC["② 実績調停<br/>(Supporting / ACL)"]
    WF["③ 業務フロー協働<br/>(Supporting)"]
    VIZ["④ 可視化<br/>(Supporting)"]

    PC -->|"C-S: コンテキスト注入"| CORE
    LLM -.->|"ACL: provider 抽象"| CORE
    LLM -.->|"ACL: provider 抽象"| WF
    CORE <==>|"Shared Kernel:<br/>analysis_result.json<br/>confidence / OperationScenario"| REC
    LE ==>|"PL: pending.json + ② に ACL"| REC
    CORE -->|"C-S: 確定UC（#5 未）"| WF
    WF ==>|"PL: 承認済みフロー（#5 未）"| LE
    CORE -->|"C-S: 抽出物"| VIZ
    REC -.->|"merged を可視化"| VIZ

    classDef core fill:#fff3e0,stroke:#FF9800,stroke-width:3px
    classDef supporting fill:#e8f5e9,stroke:#2E7D32
    classDef generic fill:#eceff1,stroke:#607D8B
    classDef external fill:#e8f4fd,stroke:#2196F3
    class CORE core
    class REC,WF,VIZ supporting
    class PC,LLM generic
    class LE external
```

凡例: `C-S` = Customer-Supplier（U→D）/ `PL` = Published Language / `ACL` = Anticorruption Layer /
`Shared Kernel` = 小さな共有モデル / `==>` = Published Language 境界 / `<==>` = Shared Kernel / `-.->` = ACL 隔離。

## 関係一覧

| # | Upstream | Downstream | 関係 | 統合方式 | 状態 |
|---|----------|-----------|------|---------|------|
| R1 | プロジェクトコンテキスト構築 | ① 要求モデル抽出 | Customer-Supplier | 関数注入（`project_context`） | ✅ |
| R2 | LLM 抽象 | ① 要求モデル抽出 / ③ | ACL（消費側で隔離） | `llm/provider.py` 抽象インターフェース | ✅（③分は #5 未） |
| R3+R8 | ① 要求モデル抽出 ⇔ ② 実績調停 | （双方向） | **Shared Kernel** | `analysis_result.json` ＋ `confidence` / `OperationScenario` 型 | ✅ |
| R4 | **loop-e2e（外部）** | ② 実績調停 | **Published Language ＋ ACL** | `loop-e2e-pending.json`（`reconcile` が `normalize_route` で翻訳） | ✅ |
| R5 | ① 要求モデル抽出 | ③ 業務フロー協働 | Customer-Supplier | 確定 UC 群（同一 `analysis_result.json` 由来） | 🔴 未（#5） |
| R6 | ③ 業務フロー協働 | **loop-e2e（外部）** | **Published Language** | 承認済み業務フローの引き渡し | 🔴 未（#5） |
| R7 | ① 要求モデル抽出 | ④ 可視化 | Customer-Supplier | 抽出物（`mermaid_renderer` / `viewer`） | ✅ |
| R9 | ② 実績調停 | ④ 可視化 | Conformist | merged `analysis_result.json` を可視化 | 🟡 |

## 統合の詳細

### R3+R8 ① 要求モデル抽出 ⇔ ② 実績調停 — Shared Kernel
- **関係**: Shared Kernel（双方向）。② は ① の出力を読み、新規UC・救済・矛盾を同一成果物へマージし返す。
- **共有モデル**: `analysis_result.json`（UC 集合）＋ 型 `confidence`（`confidence.py`）・`OperationScenario`/`OperationStep`（`scenario_builder`）。
- **統合方式**: ファイル共有（`apply_reconcile` が読み→検証→書き戻し）。`validate()` で参照整合性チェック後のみ書き戻す。
- **境界規律**: 共有は**小さく**保つ。② の救済（棄却→確定昇格・#1 follow-on）と矛盾（#4・コードを真で UC 不変）は Shared Kernel を介す。confidence の意味（confirmed/derived/inferred）を両 BC で一致させる責務。

### R4 loop-e2e → ② 実績調停 — Published Language ＋ ACL
- **関係**: loop-e2e が上流（実績供給）、② が下流。② が腐敗防止層。
- **流れるデータ**: `loop-e2e-pending.json`（実績シナリオ）。
- **統合方式**: Published Language（rdra-export スキーマ）。② の `normalize_route` は loop-e2e spec と**同一実装**＝共有言語の翻訳契約。
- **ACL の役割**: 外部スキーマを内部 `Usecase`/`OperationScenario` へ翻訳し、Core を loop-e2e の変更から隔離。「コードを真」（#4）は ACL 内の調停ルール。

### R6 ③ 業務フロー協働 → loop-e2e — Published Language（未実装）
- **関係**: ③ が上流（承認済み業務フロー供給）、loop-e2e が下流（テスト作成・実行）。
- **境界**: ③ の責務は「生成＋PdM 承認」まで。テスト作成・E2E 実行は越境しない（loop-e2e へ委譲）。
- **状態**: #5（業務フロー協働 BC）deferred ＝ この PL も未実装。Phase 5/9–11 が前提。

### R2 LLM 抽象 → ①/③ — ACL（消費側隔離）
- **関係**: Generic 上流。`llm/provider.py` の抽象インターフェースに Anthropic API / Claude Code CLI が適合。
- **統合方式**: 消費側 ACL。① は具体プロバイダを知らず provider 抽象にのみ依存＝代替可能（Generic の所以）。

## #7（コード構造リファクタ）への含意

関係種別が確定したことで sync #7 の前提が外れた。Shared Kernel（R3+R8）と Published Language（R4/R6）が
パッケージ境界の指針になる:

- **`shared/`** ← Shared Kernel: `confidence` ＋ `scenario_builder`（`OperationScenario`/`OperationStep`）。①②④ が依存。
- **`extraction/`**（① Core）/ **`reconciliation/`**（② ACL）は Shared Kernel 越しに結合。ACL 翻訳（`normalize_route` 等）は `reconciliation/` 内に閉じる。
- **`workflow/`**（③）/ **`visualization/`**（④）/ **`llm/`** / **`context/`**（Generic）。
- loop-e2e との PL スキーマ（pending.json）は `reconciliation/` の公開境界に置く。

→ ✅ **sync #7 で実装済**（別 PR `refactor/bc-aligned-packages`）。`shared/`＝Shared Kernel、`reconciliation/` に ACL 翻訳を閉じ込め、各 BC パッケージへ移行。`Usecase`→`UseCase` 統一。157 passed。

## 言語の境界で発見した事実（mapping）

- **loop-e2e は単一の関係ではなく双方向の別契約**: ② への上流（実績 PL）と ③ からの下流（承認済みフロー PL）。同じ外部システムだが BC ごとに役割が反転する。
- **① と ② は対等な Partnership ではなく Shared Kernel**: Core↔Supporting の非対称があり、共有を `analysis_result.json` ＋少数の型に限定して結合を管理する方が健全。

## 未解決の問い

- Shared Kernel（`analysis_result.json`）のスキーマ所有者は ① か、共同管理か（Phase 5/6 で版管理方針）。
- ④ 可視化は Conformist でよいか、Open Host（ビューワー API）化する余地はあるか（将来）。
- R5/R6（③ 業務フロー協働の PL）は #5 実装時に具体化（Phase 5/9–11 後）。
