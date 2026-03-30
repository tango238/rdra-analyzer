# Django (Python)

## 検出条件
- requirements.txt, pyproject.toml, Pipfile に "django" が含まれる
- manage.py が存在する

## プロジェクト構成
- manage.py — Django管理コマンド
- <project>/settings.py — 設定
- <project>/urls.py — プロジェクトレベルURLルーティング
- <app>/urls.py — アプリレベルURLルーティング
- <app>/views.py — ビュー（コントローラー相当）
- <app>/models.py — モデル定義
- <app>/serializers.py — DRFシリアライザー（API用）
- <app>/admin.py — 管理画面設定
- <app>/forms.py — フォーム定義
- <app>/templates/ — HTMLテンプレート
- <app>/migrations/ — マイグレーション

## ルーティング形式
```python
# urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

urlpatterns = [
    path('api/users/', views.UserListView.as_view()),
    path('api/users/<int:pk>/', views.UserDetailView.as_view()),
    path('api/', include(router.urls)),
]

router = DefaultRouter()
router.register('articles', ArticleViewSet)
```
- Django REST Framework (DRF) の ViewSet + Router で RESTful API を自動生成
- path() で個別ルート定義、include() でアプリのURLをインクルード

## モデル形式
```python
class User(models.Model):
    name = models.CharField(max_length=100)
    email = models.EmailField(unique=True)
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
```
- リレーション: ForeignKey, OneToOneField, ManyToManyField
- on_delete で削除時の動作を指定（CASCADE, SET_NULL, PROTECT等）

## ビュー形式
```python
# Class-based views (DRF)
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer

# Function-based views
@api_view(['GET', 'POST'])
def user_list(request):
    ...
```
