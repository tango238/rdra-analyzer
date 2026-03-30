# Gin (Go)

## 検出条件
- go.mod に "github.com/gin-gonic/gin" が含まれる

## プロジェクト構成
- main.go — エントリーポイント
- cmd/ — メインアプリケーション
- internal/ — 内部パッケージ
  - handler/ または controller/ — HTTPハンドラー
  - service/ — ビジネスロジック
  - repository/ — データアクセス
  - model/ — データモデル（構造体）
  - middleware/ — ミドルウェア
  - router/ — ルーター設定
- pkg/ — 外部公開パッケージ
- config/ — 設定
- migrations/ — マイグレーション

## ルーティング形式
```go
r := gin.Default()

api := r.Group("/api/v1")
{
    api.GET("/users", handler.ListUsers)
    api.GET("/users/:id", handler.GetUser)
    api.POST("/users", handler.CreateUser)
    api.PUT("/users/:id", handler.UpdateUser)
    api.DELETE("/users/:id", handler.DeleteUser)
}

admin := api.Group("/admin")
admin.Use(middleware.AuthRequired())
{
    admin.GET("/stats", handler.GetStats)
}
```
- r.Group() でルートグループ化（プレフィックス累積）
- :id でパスパラメータ

## モデル形式（GORM）
```go
type User struct {
    gorm.Model
    Name      string    `json:"name" gorm:"not null"`
    Email     string    `json:"email" gorm:"uniqueIndex"`
    Posts     []Post    `json:"posts" gorm:"foreignKey:UserID"`
    CompanyID uint      `json:"company_id"`
    Company   Company   `json:"company" gorm:"constraint:OnDelete:CASCADE"`
}
```
- gorm struct タグでDB制約を定義
- json タグでJSONシリアライズ名を定義
- リレーション: foreignKey, many2many, belongsTo（GORM規約ベース）

## ハンドラー形式
```go
func (h *Handler) ListUsers(c *gin.Context) {
    users, err := h.service.ListUsers(c.Request.Context())
    if err != nil {
        c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
        return
    }
    c.JSON(http.StatusOK, users)
}
```
