# View Analysis Design — ui.yml スキーマベースの画面抽出

## 概要

rdra-analyzer の画面分析機能を、teamkit の `ui.yml` スキーマに合わせて再設計する。
既存の `ScreenSpec` / `UIElement` モデルと `screen_specs.json` 出力を、`ViewScreen` 系モデルと `ui.yml` 出力に置き換える。

## 目的

- 画面（screen）、入力・表示項目（fields）、アクション（actions）をソースコードから抽出する
- teamkit 互換の `ui.yml` 形式で出力し、mokkun でのプレビューや他ツールとの相互運用を可能にする

## スコープ

### 含む

- `ui.yml` スキーマベースのデータモデル（`ViewScreen`, `ViewSection`, `ViewField`, `ViewAction`）
- LLM プロンプトの `ui.yml` スキーマ対応
- 出力フォーマットを `screen_specs.json` → `ui.yml` に変更
- `related_models` / `related_usecases` の抽出
- viewer の「画面」タブの更新
- 依存コード（`scenario_builder`, `scenario_verifier`, `main.py`）の参照更新

### 含まない

- 画面遷移（`screenflow.md`）の生成
- アクションの遷移先（`to` フィールド）
- バリデーションルール（`validations` セクション）
- wizard、conditions（`visible_when`）
- `common_components`

## データモデル

`analyzer/view_model.py` に新規作成する。

### ViewField

```python
@dataclass
class ViewField:
    id: str                         # snake_case フィールドID
    type: str                       # text, select, data_table, date_picker, number, textarea, etc.
    label: str                      # 日本語ラベル
    required: bool = False
    readonly: bool = False
    placeholder: str = ""
    options: list[dict] = field(default_factory=list)    # [{value, label}]
    columns: list[dict] = field(default_factory=list)    # data_table 用
    extra: dict = field(default_factory=dict)             # type 固有プロパティ
```

### ViewSection

```python
@dataclass
class ViewSection:
    section_name: str               # 日本語セクション名
    input_fields: list[ViewField] = field(default_factory=list)
```

### ViewAction

```python
@dataclass
class ViewAction:
    id: str
    type: str                       # submit, custom, reset
    label: str                      # 日本語ラベル
    style: str = "primary"          # primary, secondary, danger, link
    confirm: dict | None = None     # {title, message}
```

### ViewScreen

```python
@dataclass
class ViewScreen:
    screen_id: str                  # snake_case 画面ID
    title: str
    description: str
    actor: str
    purpose: str
    sections: list[ViewSection] = field(default_factory=list)
    actions: list[ViewAction] = field(default_factory=list)
    related_models: list[str] = field(default_factory=list)
    related_usecases: list[str] = field(default_factory=list)
```

### 設計判断

- `ViewAction` に `to`（遷移先）を含めない。画面遷移情報はスコープ外。
- `ViewField.extra` で `rows`, `min`, `max`, `unit`, `format` 等の type 固有プロパティを柔軟に保持する。スキーマを過度に厳密にせず、LLM 出力の多様性を吸収する。
- `options` は `[{value, label}]` 形式を正とするが、フラット文字列配列が返された場合はパーサで変換する。

## LLM 抽出

### 処理フロー

`ScreenAnalyzer` のクラス構造とバッチ処理ロジックは維持する。

1. **共有レイアウト抽出** — 現行のまま維持。出力はメニュー項目として参考情報に留め、`ViewScreen` には注入しない。
2. **個別ページのバッチ抽出** — プロンプトを `ui.yml` スキーマで返すように変更。
3. ~~ナビゲーショングラフ構築~~ — 削除。
4. ~~共有レイアウト注入~~ — 削除。

### プロンプト方針

LLM には JSON 形式で応答させ（パース安定性のため）、Python 側で YAML に変換して保存する。

プロンプトで指示する抽出ルール:

- `screen_id`: ルートパスから snake_case で生成（例: `/admin/hotels` → `admin_hotel_list`）
- `title`: ページの見出し（h1、タイトル等）から日本語で
- `actor`: ページが属するユーザーロール
- `sections`: フォーム入力を論理的なセクションにグルーピング
- `input_fields.type`: `text`, `select`, `data_table`, `date_picker`, `number`, `textarea`, `checkbox`, `radio_group`, `toggle`, `file_upload` 等
- `actions`: 画面レベルのボタン（保存、削除、新規作成など）
- `related_models`: 画面が操作するエンティティ名（日本語）
- `related_usecases`: 画面が対応するユースケース名（日本語）

### フォールバック

LLM 抽出が失敗した場合、`ParsedPage` から最低限の `ViewScreen` を生成:

- `screen_id`: `file_path` から生成
- `title`: `component_name`
- `sections`: `ParsedPage.form_fields` を 1 セクションにまとめる
- `actions`: 空

## 出力フォーマット

### 変更

| 現行 | 変更後 |
|------|--------|
| `output/usecases/screen_specs.json` | `output/usecases/ui.yml` |
| `ScreenAnalyzer.save_to_json()` | `save_to_yaml()` |
| `ScreenAnalyzer.load_from_json()` | `load_from_yaml()` |

### ui.yml 出力例

```yaml
view:
  hotel_list:
    title: "ホテル一覧"
    description: "登録済みホテルの一覧表示・検索"
    actor: "管理者"
    purpose: "ホテル情報の管理"
    sections:
      - section_name: "検索・フィルター"
        input_fields:
          - id: "search_keyword"
            type: "text"
            label: "キーワード検索"
            placeholder: "ホテル名で検索"
      - section_name: "ホテル一覧"
        input_fields:
          - id: "hotel_table"
            type: "data_table"
            label: "ホテル一覧"
            columns:
              - id: "name"
                label: "ホテル名"
                sortable: true
              - id: "address"
                label: "住所"
              - id: "status"
                label: "ステータス"
    actions:
      - id: "create_hotel"
        type: "submit"
        label: "新規作成"
        style: "primary"
      - id: "delete_hotel"
        type: "submit"
        label: "削除"
        style: "danger"
        confirm:
          title: "削除確認"
          message: "このホテルを削除してもよろしいですか？"
    related_models:
      - "ホテル"
    related_usecases:
      - "ホテル一覧の表示"
      - "ホテルの新規登録"

  hotel_form:
    title: "ホテル登録"
    description: "ホテル情報の新規登録・編集"
    actor: "管理者"
    purpose: "ホテル情報の登録"
    sections:
      - section_name: "基本情報"
        input_fields:
          - id: "hotel_name"
            type: "text"
            label: "ホテル名"
            required: true
          - id: "address"
            type: "text"
            label: "住所"
            required: true
          - id: "description"
            type: "textarea"
            label: "説明"
            placeholder: "ホテルの説明を入力"
    actions:
      - id: "save"
        type: "submit"
        label: "保存"
        style: "primary"
      - id: "cancel"
        type: "custom"
        label: "キャンセル"
        style: "secondary"
    related_models:
      - "ホテル"
    related_usecases:
      - "ホテルの新規登録"
      - "ホテルの編集"
```

## Viewer 更新

### 「画面」タブ

既存の詳細パネルパターン（シナリオ詳細と同じ）を踏襲する。

**左: 画面一覧テーブル**

| 列 | 内容 |
|----|------|
| 画面ID | `screen_id` |
| タイトル | `title` |
| アクター | `actor` |
| セクション数 | `len(sections)` |
| フィールド数 | 全セクションの `input_fields` 合計 |

**右: 詳細パネル（行クリックで表示）**

- タイトル、description、actor、purpose
- セクションごとのフィールド一覧（type, label, required をテーブル表示）
- アクション一覧（label, type, style）
- `related_models` / `related_usecases`（クリッカブルリンクで他タブへ遷移）

## 影響を受けるファイル

| ファイル | 変更内容 |
|---------|---------|
| `analyzer/view_model.py` | **新規作成** — `ViewScreen`, `ViewSection`, `ViewField`, `ViewAction` |
| `analyzer/screen_analyzer.py` | モデル差し替え、プロンプト書き換え、`save_to_yaml()`/`load_from_yaml()` 追加、ナビゲーショングラフ関連削除 |
| `analyzer/scenario_builder.py` | `ScreenSpec` 参照を `ViewScreen` に変更 |
| `analyzer/scenario_verifier.py` | `form_fields`/`action_buttons` 参照を `sections`/`actions` に変更 |
| `rdra/viewer_template.py` | 「画面」タブのレンダリングを更新 |
| `main.py` | `screen_specs.json` → `ui.yml` パス変更 |

## 変更しないファイル

- `analyzer/source_parser.py` — `ParsedPage` は入力データなのでそのまま
- `analyzer/usecase_extractor.py` — ユースケース抽出は画面と独立
- `rdra/information_model.py`, `rdra/state_transition.py`, `rdra/business_policy.py` — 影響なし
- `gap/crud_analyzer.py` — CRUD 分析は画面モデルに依存していない
