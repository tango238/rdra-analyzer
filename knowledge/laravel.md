# Laravel (PHP)

## 検出条件
- composer.json に "laravel/framework" が含まれる

## プロジェクト構成
- routes/web.php — Webルーティング（Blade用）
- routes/api.php — APIルーティング（/api プレフィックス付き）
- routes/api_v*.php — バージョン別APIルーティング（カスタム）
- app/Http/Controllers/ — コントローラー
- app/Models/ — Eloquentモデル（データベースモデル）
- app/Http/Requests/ — フォームリクエスト（バリデーション）
- app/Http/Middleware/ — ミドルウェア
- resources/views/ — Bladeテンプレート（ビュー）
- database/migrations/ — マイグレーション
- database/seeders/ — シーダー

## ルーティング形式
```php
Route::get('/users', [UserController::class, 'index']);
Route::post('/users', [UserController::class, 'store']);
Route::apiResource('users', UserController::class);
Route::group(['prefix' => 'admin', 'middleware' => ['auth']], function () {
    Route::get('/dashboard', [DashboardController::class, 'index']);
});
```
- apiResource は index/store/show/update/destroy の5ルートを自動生成
- Route::group のネストでプレフィックスが累積する

## モデル形式
```php
class User extends Model {
    protected $table = 'users';
    protected $fillable = ['name', 'email', 'password'];
    protected $casts = ['email_verified_at' => 'datetime'];
    public function posts() { return $this->hasMany(Post::class); }
    public function profile() { return $this->hasOne(Profile::class); }
}
```
- リレーション: hasMany, hasOne, belongsTo, belongsToMany, hasManyThrough, morphMany, morphTo
- $fillable でマスアサインメント可能なカラムを定義
- $casts で型キャストを定義

## コントローラー形式
```php
class UserController extends Controller {
    public function index() { ... }      // GET /users
    public function store(Request $request) { ... }  // POST /users
    public function show(User $user) { ... }         // GET /users/{id}
    public function update(Request $request, User $user) { ... } // PUT /users/{id}
    public function destroy(User $user) { ... }      // DELETE /users/{id}
}
```
