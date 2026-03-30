# Ruby on Rails (Ruby)

## 検出条件
- Gemfile に "rails" が含まれる

## プロジェクト構成
- config/routes.rb — ルーティング定義
- app/controllers/ — コントローラー
- app/models/ — ActiveRecordモデル
- app/views/ — ERBテンプレート（ビュー）
- db/migrate/ — マイグレーション
- db/schema.rb — データベーススキーマ
- app/serializers/ — JSONシリアライザー（API用）
- app/services/ — サービスオブジェクト
- app/jobs/ — バックグラウンドジョブ
- spec/ または test/ — テスト

## ルーティング形式
```ruby
Rails.application.routes.draw do
  resources :users                     # 7つのRESTfulルートを生成
  resources :posts, only: [:index, :show, :create]
  namespace :api do
    namespace :v1 do
      resources :articles
    end
  end
  get '/dashboard', to: 'dashboard#index'
  post '/login', to: 'sessions#create'
end
```
- resources は index/show/new/create/edit/update/destroy の7ルートを生成
- namespace でパスとコントローラーの名前空間をネスト

## モデル形式
```ruby
class User < ApplicationRecord
  has_many :posts
  has_one :profile
  belongs_to :company
  has_and_belongs_to_many :roles
  validates :name, presence: true
  validates :email, uniqueness: true
  scope :active, -> { where(active: true) }
end
```
- リレーション: has_many, has_one, belongs_to, has_and_belongs_to_many, has_many :through
- validates でバリデーション定義
- scope でクエリスコープ定義

## コントローラー形式
```ruby
class UsersController < ApplicationController
  before_action :authenticate_user!
  def index; end
  def show; end
  def create; end
  def update; end
  def destroy; end
end
```
