# Phoenix (Elixir)

## 検出条件
- mix.exs に "phoenix" が含まれる

## プロジェクト構成
- lib/<app>_web/ — Webレイヤー
  - router.ex — ルーティング定義
  - controllers/ — コントローラー
  - views/ または components/ — ビュー/LiveViewコンポーネント
  - live/ — LiveViewモジュール
  - templates/ — EExテンプレート
  - channels/ — WebSocketチャンネル
- lib/<app>/ — ビジネスロジック（コンテキスト）
  - accounts.ex — Accountsコンテキスト（例）
  - accounts/user.ex — Ectoスキーマ
- priv/repo/migrations/ — マイグレーション
- config/ — 設定ファイル

## ルーティング形式
```elixir
# router.ex
scope "/api", MyAppWeb do
  pipe_through :api

  resources "/users", UserController, except: [:new, :edit]
  resources "/posts", PostController, only: [:index, :show, :create]

  scope "/admin" do
    pipe_through :admin_auth
    resources "/stats", StatsController, only: [:index]
  end
end
```
- resources で RESTful ルートを自動生成（index, show, new, create, edit, update, delete）
- scope でパスプレフィックスとモジュールスコープを定義
- pipe_through でミドルウェア（パイプライン）を適用

## モデル形式（Ecto）
```elixir
defmodule MyApp.Accounts.User do
  use Ecto.Schema

  schema "users" do
    field :name, :string
    field :email, :string
    has_many :posts, MyApp.Blog.Post
    belongs_to :company, MyApp.Companies.Company
    many_to_many :roles, MyApp.Accounts.Role, join_through: "users_roles"
    timestamps()
  end

  def changeset(user, attrs) do
    user
    |> cast(attrs, [:name, :email])
    |> validate_required([:name, :email])
    |> unique_constraint(:email)
  end
end
```
- リレーション: has_many, belongs_to, has_one, many_to_many
- changeset でバリデーション定義

## コントローラー形式
```elixir
defmodule MyAppWeb.UserController do
  use MyAppWeb, :controller

  def index(conn, _params), do: ...
  def show(conn, %{"id" => id}), do: ...
  def create(conn, %{"user" => user_params}), do: ...
  def update(conn, %{"id" => id, "user" => user_params}), do: ...
  def delete(conn, %{"id" => id}), do: ...
end
```
