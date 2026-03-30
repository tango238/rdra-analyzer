# Flutter (Dart)

## 検出条件
- pubspec.yaml に "flutter" が含まれる

## プロジェクト構成
- lib/ — メインソースコード
  - main.dart — エントリーポイント
  - app.dart — アプリケーションルート（MaterialApp / Router）
  - router/ — ルーティング定義（GoRouter / auto_route 等）
  - screens/ または pages/ — 画面（ページ）
  - widgets/ — 共通ウィジェット
  - models/ — データモデル（Dart クラス / Freezed）
  - repositories/ — リポジトリ（API通信）
  - services/ — サービス層
  - providers/ — 状態管理（Riverpod / Provider）
  - blocs/ — 状態管理（BLoC パターン）
  - utils/ — ユーティリティ
- test/ — テスト
- pubspec.yaml — 依存パッケージ定義

## ルーティング形式（GoRouter）
```dart
final router = GoRouter(
  routes: [
    GoRoute(path: '/', builder: (context, state) => HomeScreen()),
    GoRoute(path: '/users', builder: (context, state) => UserListScreen()),
    GoRoute(path: '/users/:id', builder: (context, state) => UserDetailScreen(id: state.pathParameters['id']!)),
    GoRoute(path: '/users/new', builder: (context, state) => UserFormScreen()),
  ],
);
```

## モデル形式
```dart
class User {
  final int id;
  final String name;
  final String email;
  final Company? company;
  final List<Post> posts;

  User({required this.id, required this.name, required this.email, this.company, this.posts = const []});

  factory User.fromJson(Map<String, dynamic> json) => User(
    id: json['id'],
    name: json['name'],
    email: json['email'],
  );
}
```

## モデル形式（Freezed）
```dart
@freezed
class User with _$User {
  const factory User({
    required int id,
    required String name,
    required String email,
    Company? company,
    @Default([]) List<Post> posts,
  }) = _User;

  factory User.fromJson(Map<String, dynamic> json) => _$UserFromJson(json);
}
```

## API通信パターン
```dart
class UserRepository {
  final Dio _dio;
  Future<List<User>> getUsers() async {
    final response = await _dio.get('/api/users');
    return (response.data as List).map((e) => User.fromJson(e)).toList();
  }
}
```

## 特記事項
- Flutter はフロントエンド（モバイル/Web）のみ。バックエンドAPIは別リポジトリの場合が多い
- 画面遷移とAPI呼び出しパターンからユースケースを推定する
