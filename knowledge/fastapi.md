# FastAPI (Python)

## 検出条件
- requirements.txt, pyproject.toml, Pipfile に "fastapi" が含まれる

## プロジェクト構成
- main.py または app/main.py — アプリケーションエントリーポイント
- app/routers/ または app/api/ — ルーターモジュール
- app/models/ — SQLAlchemy / Tortoise ORM モデル
- app/schemas/ — Pydanticスキーマ（リクエスト/レスポンス定義）
- app/crud/ — CRUDユーティリティ
- app/db/ — データベース接続設定
- app/dependencies/ — 依存性注入
- alembic/ — マイグレーション（Alembic使用時）

## ルーティング形式
```python
from fastapi import APIRouter, FastAPI

app = FastAPI()
router = APIRouter(prefix="/api/v1")

@router.get("/users")
async def list_users(): ...

@router.post("/users")
async def create_user(user: UserCreate): ...

@router.get("/users/{user_id}")
async def get_user(user_id: int): ...

@router.put("/users/{user_id}")
async def update_user(user_id: int, user: UserUpdate): ...

@router.delete("/users/{user_id}")
async def delete_user(user_id: int): ...

app.include_router(router)
```
- デコレーター（@app.get, @router.post 等）でルート定義
- APIRouter でルーターを分割、prefix でパスプレフィックスを設定
- Pydantic モデルで自動バリデーション＋OpenAPIドキュメント生成

## モデル形式（SQLAlchemy）
```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True)
    posts = relationship("Post", back_populates="author")
```
- relationship で ORM リレーション定義
- back_populates で双方向リレーション

## スキーマ形式（Pydantic）
```python
class UserCreate(BaseModel):
    name: str
    email: EmailStr

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    model_config = ConfigDict(from_attributes=True)
```
