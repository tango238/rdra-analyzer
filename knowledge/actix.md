# Actix Web (Rust)

## 検出条件
- Cargo.toml に "actix-web" が含まれる

## プロジェクト構成
- src/main.rs — エントリーポイント
- src/routes/ または src/handlers/ — ルートハンドラー
- src/models/ — データモデル（構造体）
- src/db/ — データベース接続・クエリ
- src/schema.rs — Dieselスキーマ（Diesel使用時）
- src/errors/ — エラー型
- src/middleware/ — ミドルウェア
- src/config.rs — 設定
- migrations/ — マイグレーション

## ルーティング形式
```rust
// main.rs
HttpServer::new(|| {
    App::new()
        .service(
            web::scope("/api/v1")
                .route("/users", web::get().to(handlers::list_users))
                .route("/users", web::post().to(handlers::create_user))
                .route("/users/{id}", web::get().to(handlers::get_user))
                .route("/users/{id}", web::put().to(handlers::update_user))
                .route("/users/{id}", web::delete().to(handlers::delete_user))
        )
})

// マクロベース
#[get("/users")]
async fn list_users(db: web::Data<Pool>) -> impl Responder { ... }

#[post("/users")]
async fn create_user(body: web::Json<CreateUser>) -> impl Responder { ... }
```
- web::scope() でルートグループ化
- {id} でパスパラメータ
- #[get], #[post] 等のマクロでもルート定義可能

## モデル形式（Diesel）
```rust
#[derive(Queryable, Identifiable, Associations)]
#[diesel(table_name = users)]
#[diesel(belongs_to(Company))]
pub struct User {
    pub id: i32,
    pub name: String,
    pub email: String,
    pub company_id: i32,
}

#[derive(Insertable)]
#[diesel(table_name = users)]
pub struct NewUser {
    pub name: String,
    pub email: String,
}
```

## モデル形式（SeaORM）
```rust
#[derive(Clone, Debug, DeriveEntityModel)]
#[sea_orm(table_name = "users")]
pub struct Model {
    #[sea_orm(primary_key)]
    pub id: i32,
    pub name: String,
    pub email: String,
}

impl Related<super::post::Entity> for Entity {
    fn to() -> RelationDef { ... }
}
```
