"""
ビジネスポリシー抽出モジュール

ソースコードのバリデーションルール・権限チェック・ビジネスロジックから
ビジネスポリシー（ビジネスルール）を抽出し、一覧として出力する。
"""

import json
import re
from dataclasses import dataclass, field

from llm.provider import LLMProvider
from .information_model import Entity


@dataclass
class CodeReference:
    """ビジネスポリシーのコード参照"""
    file_path: str              # ファイルパス（例: app/Http/Controllers/BookingController.php）
    description: str            # 参照内容の説明（例: キャンセル期限チェック）
    code_type: str = ""         # controller / model / middleware / route / validation


@dataclass
class BusinessPolicy:
    """ビジネスポリシーの定義"""
    id: str                     # BP-001 形式
    name: str                   # ポリシー名（日本語）
    category: str               # カテゴリ（バリデーション/認可/計算/制約/ワークフロー）
    description: str            # 詳細説明
    related_entities: list[str] = field(default_factory=list)
    related_usecases: list[str] = field(default_factory=list)
    severity: str = "must"      # must / should / may
    code_references: list[CodeReference] = field(default_factory=list)


class BusinessPolicyExtractor:
    """
    ビジネスポリシーを抽出するクラス。

    1. ユースケースの事前条件・事後条件からポリシーを推定
    2. ルート定義のミドルウェア・バリデーションからポリシーを推定
    3. エンティティの制約・リレーションからポリシーを推定
    4. LLM で統合・分類・日本語化
    """

    def __init__(self, llm_provider: LLMProvider, project_context: str = ""):
        self._llm = llm_provider
        self._project_context = project_context

    def extract(
        self,
        entities: list[Entity],
        usecases: list = None,
        routes: list = None,
        controllers: list = None,
    ) -> list[BusinessPolicy]:
        """ビジネスポリシーを抽出する"""
        return self._extract_with_llm(
            entities,
            usecases or [],
            routes or [],
            controllers or [],
        )

    def _extract_with_llm(
        self,
        entities: list[Entity],
        usecases: list,
        routes: list,
        controllers: list,
    ) -> list[BusinessPolicy]:
        """LLM でビジネスポリシーを抽出する"""
        entity_info = [
            {"class_name": e.class_name, "name": e.name, "attributes": e.attributes[:15]}
            for e in entities[:40]
        ]

        uc_info = []
        for uc in usecases[:30]:
            uc_info.append({
                "id": uc.id,
                "name": uc.name,
                "actor": uc.actor,
                "preconditions": uc.preconditions,
                "postconditions": uc.postconditions,
                "related_entities": uc.related_entities,
            })

        route_info = []
        for r in routes[:60]:
            entry = {"method": r.method, "path": r.path, "controller": r.controller}
            if hasattr(r, "middleware") and r.middleware:
                entry["middleware"] = r.middleware
            route_info.append(entry)

        controller_info = []
        for c in controllers[:20]:
            entry = {"class_name": c.class_name}
            if hasattr(c, "file_path") and c.file_path:
                entry["file_path"] = c.file_path
            if hasattr(c, "request_rules") and c.request_rules:
                entry["validation_rules"] = {
                    k: v for k, v in list(c.request_rules.items())[:5]
                }
            if hasattr(c, "methods") and c.methods:
                entry["methods"] = c.methods[:10]
            controller_info.append(entry)

        system_prompt = """あなたはビジネスアナリストです。
ソフトウェアシステムからビジネスポリシー（ビジネスルール）を抽出してください。

以下のカテゴリに分類してください:
- バリデーション: 入力値の制約・形式チェック
- 認可: アクセス制御・権限管理
- 計算: 料金計算・割引・税金等のビジネスロジック
- 制約: データの整合性制約・一意性制約
- ワークフロー: 承認フロー・状態遷移の制約
- 通知: 通知条件・メール送信ルール
- 期限: 有効期限・キャンセル期限等の時間制約

severity は以下で判定:
- must: 違反するとシステムエラーや業務上の重大な問題になる
- should: 推奨されるが違反しても致命的ではない
- may: あると望ましいが必須ではない

出力はJSON配列で:
```json
[
  {
    "name": "予約キャンセル期限",
    "category": "期限",
    "description": "チェックイン日の3日前までキャンセル可能。それ以降はキャンセル料が発生する",
    "related_entities": ["Booking", "CancellationPolicy"],
    "related_usecases": ["UC-050"],
    "severity": "must",
    "code_references": [
      {
        "file_path": "app/Http/Controllers/BookingController.php",
        "description": "cancelBookingメソッドでキャンセル期限をチェック",
        "code_type": "controller"
      }
    ]
  }
]
```

code_references には、そのポリシーの根拠となるコード箇所を含めてください:
- file_path: 該当ファイルのパス（コントローラー、モデル、ミドルウェア等）
- description: そのコードが何をしているか
- code_type: controller / model / middleware / route / validation のいずれか

できるだけ具体的に、このシステム固有のビジネスルールを抽出してください。
一般的すぎるルール（「メールアドレスは必須」等）は含めないでください。"""

        user_msg = f"""以下の情報からビジネスポリシーを抽出してください。

エンティティ:
{json.dumps(entity_info, ensure_ascii=False, indent=2)}

ユースケース:
{json.dumps(uc_info, ensure_ascii=False, indent=2)}
"""
        if route_info:
            user_msg += f"\nAPIルート:\n{json.dumps(route_info, ensure_ascii=False, indent=2)}\n"
        if controller_info:
            user_msg += f"\nバリデーションルール:\n{json.dumps(controller_info, ensure_ascii=False, indent=2)}\n"
        if self._project_context:
            user_msg += f"\nプロジェクトコンテキスト:\n{self._project_context[:2000]}\n"

        response = self._llm.complete_simple(system_prompt, user_msg)
        return self._parse_response(response)

    def _parse_response(self, response: str) -> list[BusinessPolicy]:
        """LLMレスポンスをパースする"""
        json_match = re.search(r"\[.*\]", response, re.DOTALL)
        if not json_match:
            return []

        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return []

        policies = []
        for i, item in enumerate(data, 1):
            code_refs = []
            for ref in item.get("code_references", []):
                code_refs.append(CodeReference(
                    file_path=ref.get("file_path", ""),
                    description=ref.get("description", ""),
                    code_type=ref.get("code_type", ""),
                ))
            policies.append(BusinessPolicy(
                id=f"BP-{i:03d}",
                name=item.get("name", ""),
                category=item.get("category", "その他"),
                description=item.get("description", ""),
                related_entities=item.get("related_entities", []),
                related_usecases=item.get("related_usecases", []),
                severity=item.get("severity", "must"),
                code_references=code_refs,
            ))

        return policies
