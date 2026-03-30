"""
パート2: RDRAモデル生成パッケージ

ソースコードから RDRA の以下3つを生成する:
1. 情報モデル（エンティティ・属性・関係）
2. ユースケース複合図（アクター・ユースケース・条件・バリエーション）
3. アクティビティ図（操作シナリオ）

すべて Mermaid 記法の Markdown ファイルとして出力する。
"""

from .information_model import InformationModelGenerator, Entity, Relationship, InformationGroup
from .usecase_diagram import UsecaseDiagramGenerator
from .activity_diagram import ActivityDiagramGenerator
from .state_transition import StateTransitionGenerator, EntityStateMachine, StateTransition
from .business_policy import BusinessPolicyExtractor, BusinessPolicy
from .mermaid_renderer import MermaidRenderer

__all__ = [
    "InformationModelGenerator",
    "Entity",
    "Relationship",
    "InformationGroup",
    "UsecaseDiagramGenerator",
    "ActivityDiagramGenerator",
    "StateTransitionGenerator",
    "EntityStateMachine",
    "StateTransition",
    "BusinessPolicyExtractor",
    "BusinessPolicy",
    "MermaidRenderer",
]
