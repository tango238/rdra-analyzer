"""
ソースコード解析モジュール（汎用版）

CLAUDE.md / AGENTS.md をコンテキストとして活用し、
LLM（Claude Code CLI）でどんな言語・フレームワークのリポジトリでも
動的にルート・ハンドラー・モデル・ビューを抽出する。
"""

import json
import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from config import get_config
from analyzer.project_context import (
    ProjectContext,
    build_context,
    format_context_for_prompt,
)

ENTITY_BATCH_SIZE = 20

# =========================================================================
# 汎用データクラス
# =========================================================================

@dataclass
class ParsedRoute:
    """解析されたAPIルート/エンドポイント情報"""
    method: str             # HTTP メソッド（GET, POST, PUT, DELETE など）
    path: str               # APIパス（/api/v2/hotels など）
    controller: str         # ハンドラー名（コントローラー、ハンドラー、関数名など）
    action: str             # アクション/メソッド名
    middleware: list[str]   # ミドルウェア/ガード
    prefix: str = ""        # ルートグループのプレフィックス


@dataclass
class ParsedController:
    """解析されたハンドラー/コントローラー情報"""
    class_name: str             # クラス名/モジュール名
    file_path: str              # ファイルパス（プロジェクトルートからの相対パス）
    namespace: str              # 名前空間/パッケージ
    methods: list[str]          # 公開メソッド/関数一覧
    docblocks: dict[str, str]   # メソッド名→ドキュメントコメント
    request_rules: dict[str, list[str]]  # メソッド名→バリデーションルール
    entity_operations: dict[str, list] = field(default_factory=dict)
    # メソッド名 → そのメソッドから到達するEntityOperationリスト


@dataclass
class ParsedModel:
    """解析されたデータモデル/エンティティ情報"""
    class_name: str             # クラス名/構造体名
    table_name: str             # テーブル名/コレクション名（不明時は空文字）
    fillable: list[str]         # 書き込み可能フィールド/属性
    relationships: list[str]    # リレーション定義
    casts: dict[str, str]       # 型変換/キャスト定義
    scopes: list[str]           # スコープ/クエリメソッド


@dataclass
class ParsedPage:
    """解析されたビュー/ページ情報"""
    route_path: str             # URLパス
    file_path: str              # ファイルパス
    component_name: str         # コンポーネント名/テンプレート名
    page_type: str              # "list", "detail", "form", "dashboard" など
    api_calls: list[str]        # 呼び出しているAPIエンドポイント
    imported_hooks: list[str]   # データ取得フック/サービス呼び出し
    form_fields: list[str] = field(default_factory=list)
    feature_component: str = ""


@dataclass
class EntityOperation:
    """エンティティに対するCRUD操作の検出結果"""
    entity_class: str          # 操作対象のエンティティクラス名 (例: "Stock")
    operation: str             # "Create" | "Read" | "Update" | "Delete"
    method_signature: str      # 検出されたメソッド/パターン (例: "Stock::where(...)->decrement('qty')")
    source_file: str           # 操作が記述されたファイルパス
    source_class: str          # 操作が記述されたクラス名 (例: "OrderService")
    source_method: str         # 操作が記述されたメソッド名 (例: "createOrder")
    call_chain: list[str] = field(default_factory=list)  # コール階層


@dataclass
class RepoParseResult:
    """
    並列解析ワーカーがメインスレッドに返す結果コンテナ。

    成功・失敗を同一の型で扱うことで、Future.result() の呼び出し側が
    例外ハンドリングを個別に書かなくて済む。context は並列処理の外で
    prebuild するため、このクラスには含めない。
    """
    repo_name: str
    success: bool
    routes: list[ParsedRoute] = field(default_factory=list)
    controllers: list[ParsedController] = field(default_factory=list)
    models: list[ParsedModel] = field(default_factory=list)
    pages: list[ParsedPage] = field(default_factory=list)
    entity_operations: list[EntityOperation] = field(default_factory=list)
    error: Optional[str] = None


class SourceParser:
    """
    LLM駆動の汎用ソースコードパーサー。

    CLAUDE.md / AGENTS.md をコンテキストとして Claude Code CLI に渡し、
    どんな言語・フレームワークでも動的にコード構造を抽出する。
    """

    def __init__(self, llm_provider=None):
        self._config = get_config()
        self._llm = llm_provider

    def parse_repo(self, repo_path: Path) -> dict:
        """
        リポジトリを解析してルート・ハンドラー・モデル・ビューを抽出する。

        Args:
            repo_path: 解析対象リポジトリのパス

        Returns:
            dict: {
                "routes": [ParsedRoute],
                "controllers": [ParsedController],
                "models": [ParsedModel],
                "pages": [ParsedPage],
                "entity_operations": [EntityOperation],
                "project_context": ProjectContext,
            }
        """
        # プロジェクトコンテキストを構築
        ctx = build_context(repo_path)
        context_text = format_context_for_prompt([ctx])

        entity_operations: list[EntityOperation] = []

        if self._llm is not None and hasattr(self._llm, "analyze_codebase"):
            # LLM 駆動の解析
            routes = self._extract_routes_with_llm(repo_path, context_text)
            controllers = self._extract_controllers_with_llm(repo_path, context_text)
            models = self._extract_models_with_llm(repo_path, context_text)
            pages = self._extract_pages_with_llm(repo_path, context_text)
            entity_operations = self._extract_entity_operations_with_llm(
                repo_path, context_text, models
            )
            self._attach_operations_to_controllers(controllers, entity_operations)
        elif self._llm is not None:
            # Anthropic API のみ（analyze_codebase なし）→ コンテキストベースで推定
            routes = self._extract_routes_with_api(context_text)
            controllers = []
            models = self._extract_models_with_api(context_text)
            pages = []
            entity_operations = self._extract_entity_operations_with_api(
                context_text, models, controllers
            )
        else:
            # LLM なし → マニフェスト＋ディレクトリ構造からの最低限の推定
            routes = []
            controllers = []
            models = []
            pages = []

        return {
            "routes": routes,
            "controllers": controllers,
            "models": models,
            "pages": pages,
            "entity_operations": entity_operations,
            "project_context": ctx,
        }

    def parse_all_repos(self) -> dict:
        """
        設定されたすべてのリポジトリを解析して統合する。

        Returns:
            dict: 統合された解析結果
        """
        all_routes: list[ParsedRoute] = []
        all_controllers: list[ParsedController] = []
        all_models: list[ParsedModel] = []
        all_pages: list[ParsedPage] = []
        all_entity_operations: list[EntityOperation] = []
        all_contexts: list[ProjectContext] = []

        for repo_path in self._config.repo_paths:
            result = self.parse_repo(repo_path)
            all_routes.extend(result["routes"])
            all_controllers.extend(result["controllers"])
            all_models.extend(result["models"])
            all_pages.extend(result["pages"])
            all_entity_operations.extend(result.get("entity_operations", []))
            all_contexts.append(result["project_context"])

        return {
            "routes": all_routes,
            "controllers": all_controllers,
            "models": all_models,
            "pages": all_pages,
            "entity_operations": all_entity_operations,
            "project_contexts": all_contexts,
        }

    # =========================================================================
    # LLM 駆動の抽出（Claude Code CLI - analyze_codebase）
    # =========================================================================

    def _extract_routes_with_llm(
        self, repo_path: Path, context_text: str
    ) -> list[ParsedRoute]:
        """Claude Code CLI でルート/エンドポイントを抽出する"""
        prompt = f"""{context_text}

上記のプロジェクト情報を参考に、このリポジトリのAPIルート/エンドポイント定義を探して抽出してください。

手順:
1. CLAUDE.md や AGENTS.md に記載されたプロジェクト構造を参考に、ルーティング定義ファイルを特定する
2. フレームワークに応じた方法でルートを抽出する:
   - Laravel: routes/*.php
   - Rails: config/routes.rb
   - Express/Fastify: ルーターファイル（app.get, router.post 等）
   - Django: urls.py
   - Spring Boot: @RequestMapping, @GetMapping 等のアノテーション
   - FastAPI: @app.get, @router.post 等のデコレーター
   - Go (Echo/Gin/Chi): e.GET, r.Get 等のルート登録
   - その他: フレームワークに応じて適切に判断
3. 最大200件のルートを抽出する

以下のJSON形式のみを返してください（説明不要）:
{{
  "routes": [
    {{
      "method": "GET",
      "path": "/api/users",
      "controller": "UserController",
      "action": "index",
      "middleware": ["auth"],
      "prefix": "/api"
    }}
  ]
}}"""

        try:
            result_text = self._llm.analyze_codebase(
                path=str(repo_path),
                prompt=prompt,
                timeout=self._config.CLAUDE_ANALYZE_TIMEOUT,
            )
            return self._parse_routes_json(result_text)
        except Exception as e:
            import sys
            print(f"  [warn] ルート抽出に失敗: {e}", file=sys.stderr)
            return []

    def _extract_controllers_with_llm(
        self, repo_path: Path, context_text: str
    ) -> list[ParsedController]:
        """Claude Code CLI でハンドラー/コントローラーを抽出する"""
        prompt = f"""{context_text}

上記のプロジェクト情報を参考に、このリポジトリの主要なコントローラー/ハンドラー/ルートハンドラーを抽出してください。

手順:
1. CLAUDE.md や AGENTS.md の情報をもとに、ビジネスロジックを含むハンドラー層を特定する
2. 各ハンドラーのクラス名（またはモジュール名）、公開メソッド、バリデーションルールを抽出
3. 最大50件を対象とする

以下のJSON形式のみを返してください（説明不要）:
{{
  "controllers": [
    {{
      "class_name": "UserController",
      "file_path": "app/Http/Controllers/UserController.php",
      "namespace": "App\\Http\\Controllers",
      "methods": ["index", "show", "store", "update", "destroy"],
      "docblocks": {{"index": "ユーザー一覧を取得"}},
      "request_rules": {{"store": ["name", "email", "password"]}}
    }}
  ]
}}"""

        try:
            result_text = self._llm.analyze_codebase(
                path=str(repo_path),
                prompt=prompt,
                timeout=self._config.CLAUDE_ANALYZE_TIMEOUT,
            )
            return self._parse_controllers_json(result_text)
        except Exception as e:
            import sys
            print(f"  [warn] コントローラー抽出に失敗: {e}", file=sys.stderr)
            return []

    def _extract_models_with_llm(
        self, repo_path: Path, context_text: str
    ) -> list[ParsedModel]:
        """Claude Code CLI でデータモデル/エンティティを抽出する"""
        prompt = f"""{context_text}

上記のプロジェクト情報を参考に、このリポジトリのデータモデル/エンティティ定義を抽出してください。

手順:
1. CLAUDE.md や AGENTS.md の情報をもとに、モデル/エンティティ層を特定する
2. フレームワークに応じた方法でモデルを抽出する:
   - Laravel: app/Models/*.php（Eloquent）
   - Rails: app/models/*.rb（ActiveRecord）
   - Django: models.py（Django ORM）
   - Spring Boot: @Entity アノテーション（JPA）
   - SQLAlchemy: Model クラス
   - Prisma: schema.prisma
   - TypeORM: @Entity デコレーター
   - Go: 構造体（struct）+ DB タグ
   - その他: フレームワークに応じて適切に判断
3. 各モデルのクラス名、テーブル名、フィールド、リレーションを抽出
4. 最大100件を対象とする

以下のJSON形式のみを返してください（説明不要）:
{{
  "models": [
    {{
      "class_name": "User",
      "table_name": "users",
      "fillable": ["name", "email", "password"],
      "relationships": ["posts (hasMany)", "profile (hasOne)"],
      "casts": {{"email_verified_at": "datetime"}},
      "scopes": ["active", "admin"]
    }}
  ]
}}"""

        try:
            result_text = self._llm.analyze_codebase(
                path=str(repo_path),
                prompt=prompt,
                timeout=self._config.CLAUDE_ANALYZE_TIMEOUT,
            )
            return self._parse_models_json(result_text)
        except Exception as e:
            import sys
            print(f"  [warn] モデル抽出に失敗: {e}", file=sys.stderr)
            return []

    def _extract_pages_with_llm(
        self, repo_path: Path, context_text: str
    ) -> list[ParsedPage]:
        """Claude Code CLI でビュー/ページを抽出する"""
        prompt = f"""{context_text}

上記のプロジェクト情報を参考に、このリポジトリのビュー/ページ/画面定義を抽出してください。

手順:
1. CLAUDE.md や AGENTS.md の情報をもとに、UI層（ページ/ビュー/テンプレート）を特定する
2. フレームワークに応じた方法でページを抽出する:
   - Next.js: app/**/page.tsx または pages/**/*.tsx
   - Nuxt: pages/**/*.vue
   - React Router: ルート定義コンポーネント
   - Vue Router: router 定義
   - Rails: app/views/**/*.erb
   - Django: templates/**/*.html
   - Blade (Laravel): resources/views/**/*.blade.php
   - Svelte: src/routes/**/*.svelte
   - その他: フレームワークに応じて適切に判断
3. もしフロントエンドが存在しないAPI専用プロジェクトの場合は、空の配列を返す
4. 各ページのURLパス、ファイルパス、種別（一覧/詳細/フォーム等）、API呼び出しを抽出
5. 最大50件を対象とする

以下のJSON形式のみを返してください（説明不要）:
{{
  "pages": [
    {{
      "route_path": "/users",
      "file_path": "app/(dashboard)/users/page.tsx",
      "component_name": "UserList",
      "page_type": "list",
      "api_calls": ["GET /api/users"],
      "imported_hooks": ["useUsersIndex"],
      "form_fields": [],
      "feature_component": ""
    }}
  ]
}}"""

        try:
            result_text = self._llm.analyze_codebase(
                path=str(repo_path),
                prompt=prompt,
                timeout=self._config.CLAUDE_ANALYZE_TIMEOUT,
            )
            return self._parse_pages_json(result_text)
        except Exception as e:
            import sys
            print(f"  [warn] ページ抽出に失敗: {e}", file=sys.stderr)
            return []

    def _extract_entity_operations_with_llm(
        self, repo_path: Path, context_text: str, models: list[ParsedModel]
    ) -> list[EntityOperation]:
        """エンティティモデルからCRUD操作を検出し、コントローラーまで遡って追跡する"""
        if not models:
            return []

        if len(models) <= ENTITY_BATCH_SIZE:
            return self._extract_entity_operations_batch(repo_path, context_text, models)

        all_operations: list[EntityOperation] = []
        for i in range(0, len(models), ENTITY_BATCH_SIZE):
            batch = models[i:i + ENTITY_BATCH_SIZE]
            operations = self._extract_entity_operations_batch(repo_path, context_text, batch)
            all_operations.extend(operations)
        return all_operations

    def _extract_entity_operations_batch(
        self, repo_path: Path, context_text: str, models: list[ParsedModel]
    ) -> list[EntityOperation]:
        """エンティティ操作をバッチ単位でLLM抽出する"""
        entity_list = "\n".join(
            f"- {m.class_name} (table: {m.table_name})" for m in models
        )

        prompt = f"""{context_text}

## 対象エンティティ
{entity_list}

## 指示

上記のエンティティに対するCRUD操作を、ソースコードから検出してください。

### 優先順位
1. CLAUDE.md / AGENTS.md に記載されたアーキテクチャ・規約（最優先）
2. プロジェクトの実際のソースコード
3. フレームワーク知識（上記が不明確な場合のフォールバック）

### 手順
1. 各エンティティのモデル/エンティティクラスのソースコードを確認する
2. そのエンティティに対してCreate/Read/Update/Deleteを行っているコードを
   プロジェクト全体から探す（Controller, Service, Repository, Job, EventListener等）
3. 各操作について、呼び出し元をControllerメソッドまで遡って追跡する
4. 1つのControllerメソッドが複数エンティティを操作している場合、すべて記録する

### 注意
- HTTPメソッドではなく、実際のコード上のCRUD操作で判断すること
- 間接的な操作も検出すること
  例: OrderController.store() → OrderService.createOrder() → Stock::decrement()
  この場合 Stock に対する Update 操作として記録
- Cascade削除やイベントリスナー経由の操作も可能な範囲で検出する

以下のJSON形式のみを返してください（説明不要）:
{{{{
  "entity_operations": [
    {{{{
      "entity_class": "Stock",
      "operation": "Update",
      "method_signature": "Stock::where(...)->decrement('qty')",
      "source_file": "app/Services/OrderService.php",
      "source_class": "OrderService",
      "source_method": "createOrder",
      "call_chain": ["OrderController.store", "OrderService.createOrder"]
    }}}}
  ]
}}}}"""

        try:
            result_text = self._llm.analyze_codebase(
                path=str(repo_path),
                prompt=prompt,
                timeout=self._config.CLAUDE_ANALYZE_TIMEOUT,
            )
            return self._parse_entity_operations_json(result_text)
        except Exception as e:
            import sys
            print(f"  [warn] エンティティ操作抽出に失敗: {e}", file=sys.stderr)
            return []

    # =========================================================================
    # Anthropic API のみ（analyze_codebase なし）でのコンテキストベース抽出
    # =========================================================================

    def _extract_routes_with_api(self, context_text: str) -> list[ParsedRoute]:
        """プロジェクトコンテキストからLLMでルートを推定する"""
        system_prompt = "あなたはソフトウェアアーキテクチャの専門家です。プロジェクト情報からAPIルートを推定してください。"
        user_message = f"""{context_text}

上記の情報から、このプロジェクトに存在すると推定されるAPIルートを抽出してください。
CLAUDE.md やディレクトリ構造から読み取れる範囲で推定してください。

以下のJSON形式のみで返してください:
{{
  "routes": [
    {{"method": "GET", "path": "/api/users", "controller": "UserController", "action": "index", "middleware": [], "prefix": ""}}
  ]
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=system_prompt,
            )
            return self._parse_routes_json(response)
        except Exception:
            return []

    def _extract_models_with_api(self, context_text: str) -> list[ParsedModel]:
        """プロジェクトコンテキストからLLMでモデルを推定する"""
        system_prompt = "あなたはソフトウェアアーキテクチャの専門家です。プロジェクト情報からデータモデルを推定してください。"
        user_message = f"""{context_text}

上記の情報から、このプロジェクトに存在すると推定されるデータモデル/エンティティを抽出してください。
CLAUDE.md やディレクトリ構造から読み取れる範囲で推定してください。

以下のJSON形式のみで返してください:
{{
  "models": [
    {{"class_name": "User", "table_name": "users", "fillable": ["name", "email"], "relationships": [], "casts": {{}}, "scopes": []}}
  ]
}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=system_prompt,
            )
            return self._parse_models_json(response)
        except Exception:
            return []

    def _extract_entity_operations_with_api(
        self, context_text: str, models: list[ParsedModel], controllers: list[ParsedController]
    ) -> list[EntityOperation]:
        """プロジェクトコンテキストからLLMでエンティティ操作を推定する"""
        entity_list = "\n".join(
            f"- {m.class_name} (table: {m.table_name})" for m in models
        )
        controller_list = "\n".join(
            f"- {c.class_name}: {', '.join(c.methods)}" for c in controllers
        )

        system_prompt = "あなたはソフトウェアアーキテクチャの専門家です。プロジェクト情報からエンティティのCRUD操作を推定してください。"
        user_message = f"""{context_text}

## 対象エンティティ
{entity_list}

## コントローラー一覧
{controller_list}

上記の情報から、各エンティティに対するCRUD操作とその呼び出し元を推定してください。
CLAUDE.md / AGENTS.md の規約を最優先し、次にフレームワーク知識で推定してください。

以下のJSON形式のみで返してください:
{{{{
  "entity_operations": [
    {{{{
      "entity_class": "User",
      "operation": "Create",
      "method_signature": "",
      "source_file": "",
      "source_class": "UserController",
      "source_method": "store",
      "call_chain": ["UserController.store"]
    }}}}
  ]
}}}}"""

        try:
            response = self._llm.complete_simple(
                user_message=user_message,
                system_prompt=system_prompt,
            )
            return self._parse_entity_operations_json(response)
        except Exception:
            return []

    # =========================================================================
    # JSON パース
    # =========================================================================

    def _extract_json(self, text: str) -> dict:
        """テキストからJSON部分を抽出してパースする"""
        cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
        cleaned = re.sub(r"```\s*$", "", cleaned).strip()

        json_match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not json_match:
            return {}
        return json.loads(json_match.group(0))

    def _parse_routes_json(self, text: str) -> list[ParsedRoute]:
        """JSON テキストを ParsedRoute リストに変換する"""
        try:
            data = self._extract_json(text)
        except (json.JSONDecodeError, ValueError):
            return []

        routes: list[ParsedRoute] = []
        for item in data.get("routes", []):
            routes.append(ParsedRoute(
                method=item.get("method", "GET"),
                path=item.get("path", ""),
                controller=item.get("controller", ""),
                action=item.get("action", ""),
                middleware=item.get("middleware", []),
                prefix=item.get("prefix", ""),
            ))
        return routes

    def _parse_controllers_json(self, text: str) -> list[ParsedController]:
        """JSON テキストを ParsedController リストに変換する"""
        try:
            data = self._extract_json(text)
        except (json.JSONDecodeError, ValueError):
            return []

        controllers: list[ParsedController] = []
        for item in data.get("controllers", []):
            controllers.append(ParsedController(
                class_name=item.get("class_name", ""),
                file_path=item.get("file_path", ""),
                namespace=item.get("namespace", ""),
                methods=item.get("methods", []),
                docblocks=item.get("docblocks", {}),
                request_rules=item.get("request_rules", {}),
            ))
        return controllers

    def _parse_models_json(self, text: str) -> list[ParsedModel]:
        """JSON テキストを ParsedModel リストに変換する"""
        try:
            data = self._extract_json(text)
        except (json.JSONDecodeError, ValueError):
            return []

        models: list[ParsedModel] = []
        for item in data.get("models", []):
            models.append(ParsedModel(
                class_name=item.get("class_name", ""),
                table_name=item.get("table_name", ""),
                fillable=item.get("fillable", []),
                relationships=item.get("relationships", []),
                casts=item.get("casts", {}),
                scopes=item.get("scopes", []),
            ))
        return models

    def _parse_pages_json(self, text: str) -> list[ParsedPage]:
        """JSON テキストを ParsedPage リストに変換する"""
        try:
            data = self._extract_json(text)
        except (json.JSONDecodeError, ValueError):
            return []

        pages: list[ParsedPage] = []
        for item in data.get("pages", []):
            pages.append(ParsedPage(
                route_path=item.get("route_path", ""),
                file_path=item.get("file_path", ""),
                component_name=item.get("component_name", ""),
                page_type=item.get("page_type", "list"),
                api_calls=item.get("api_calls", []),
                imported_hooks=item.get("imported_hooks", []),
                form_fields=item.get("form_fields", []),
                feature_component=item.get("feature_component", ""),
            ))
        return pages

    def _attach_operations_to_controllers(
        self,
        controllers: list[ParsedController],
        operations: list[EntityOperation],
    ) -> None:
        """EntityOperationのcall_chainからコントローラーメソッドを特定し紐付ける"""
        ctrl_index: dict[str, ParsedController] = {}
        for ctrl in controllers:
            ctrl_index[ctrl.class_name] = ctrl

        for op in operations:
            if not op.call_chain:
                continue

            first = op.call_chain[0]
            if "." not in first:
                continue

            ctrl_name, method_name = first.rsplit(".", 1)
            ctrl = ctrl_index.get(ctrl_name)
            if ctrl is None:
                continue

            if method_name not in ctrl.entity_operations:
                ctrl.entity_operations[method_name] = []
            ctrl.entity_operations[method_name].append(op)

    def _parse_entity_operations_json(self, text: str) -> list[EntityOperation]:
        """JSON テキストを EntityOperation リストに変換する"""
        try:
            data = self._extract_json(text)
        except (json.JSONDecodeError, ValueError):
            return []

        operations: list[EntityOperation] = []
        for item in data.get("entity_operations", []):
            operations.append(EntityOperation(
                entity_class=item.get("entity_class", ""),
                operation=item.get("operation", ""),
                method_signature=item.get("method_signature", ""),
                source_file=item.get("source_file", ""),
                source_class=item.get("source_class", ""),
                source_method=item.get("source_method", ""),
                call_chain=item.get("call_chain", []),
            ))
        return operations
