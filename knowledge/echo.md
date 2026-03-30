# Echo (Go)

## 検出条件
- go.mod に "github.com/labstack/echo" が含まれる

## プロジェクト構成
- main.go — エントリーポイント
- cmd/ — メインアプリケーション
- internal/ — 内部パッケージ
  - handler/ — HTTPハンドラー
  - service/ — ビジネスロジック
  - repository/ — データアクセス
  - model/ — データモデル（構造体）
  - middleware/ — ミドルウェア
- pkg/ — 外部公開パッケージ
- config/ — 設定

## ルーティング形式
```go
e := echo.New()

api := e.Group("/api/v1")
api.GET("/users", handler.ListUsers)
api.GET("/users/:id", handler.GetUser)
api.POST("/users", handler.CreateUser)
api.PUT("/users/:id", handler.UpdateUser)
api.DELETE("/users/:id", handler.DeleteUser)

admin := api.Group("/admin", middleware.Auth)
admin.GET("/stats", handler.GetStats)
```
- e.Group() でルートグループ化
- :id でパスパラメータ

## モデル形式（GORM / ent）
```go
// GORM
type User struct {
    ID        uint      `json:"id" gorm:"primaryKey"`
    Name      string    `json:"name"`
    Email     string    `json:"email" gorm:"uniqueIndex"`
    Posts     []Post    `json:"posts"`
    CompanyID uint      `json:"company_id"`
    Company   Company   `json:"company"`
}
```

## ハンドラー形式
```go
func (h *Handler) ListUsers(c echo.Context) error {
    users, err := h.service.ListUsers(c.Request().Context())
    if err != nil {
        return c.JSON(http.StatusInternalServerError, map[string]string{"error": err.Error()})
    }
    return c.JSON(http.StatusOK, users)
}
```
