"""
パート3: CRUDギャップ分析パッケージ

情報モデルの各エンティティに対して
Create/Read/Update/Delete の操作シナリオが存在するかを確認し、
不足しているCRUD操作を一覧出力する。
"""

from .crud_analyzer import CrudAnalyzer, CrudGap, EntityCrudStatus

__all__ = [
    "CrudAnalyzer",
    "CrudGap",
    "EntityCrudStatus",
]
