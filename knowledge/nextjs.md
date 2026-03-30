# Next.js (React / TypeScript)

## 検出条件
- package.json に "next" が含まれる

## プロジェクト構成（App Router — Next.js 13+）
- app/ — App Router ルートディレクトリ
  - layout.tsx — 共通レイアウト
  - page.tsx — ルートページ（/ に対応）
  - (dashboard)/ — ルートグループ（URLに影響しない）
  - users/page.tsx — /users ページ
  - users/[id]/page.tsx — /users/:id ページ
  - users/new/page.tsx — /users/new ページ
  - api/ — APIルート（Route Handlers）
    - users/route.ts — GET/POST /api/users
    - users/[id]/route.ts — GET/PUT/DELETE /api/users/:id
- components/ — 共通コンポーネント
- features/ — 機能別コンポーネント（ビジネスロジック）
- lib/ または utils/ — ユーティリティ
- hooks/ — カスタムフック

## プロジェクト構成（Pages Router — レガシー）
- pages/ — ファイルベースルーティング
  - index.tsx — / ページ
  - users/index.tsx — /users ページ
  - users/[id].tsx — /users/:id ページ
  - api/ — APIルート
    - users.ts — /api/users
    - users/[id].ts — /api/users/:id

## ルーティング形式
- ファイルシステムベース: ディレクトリ構造がそのままURLパスになる
- [id] — 動的ルートパラメータ
- [...slug] — キャッチオールルート
- (group) — ルートグループ（URLに含まれない）

## API Route Handler 形式（App Router）
```typescript
// app/api/users/route.ts
export async function GET(request: Request) { ... }
export async function POST(request: Request) { ... }

// app/api/users/[id]/route.ts
export async function GET(request: Request, { params }: { params: { id: string } }) { ... }
export async function PUT(request: Request, { params }: { params: { id: string } }) { ... }
export async function DELETE(request: Request, { params }: { params: { id: string } }) { ... }
```

## データ取得パターン
- SWR: `useSWR('/api/users', fetcher)` — クライアントサイド
- React Query / TanStack Query: `useQuery({ queryKey: ['users'] })`
- Server Components: `async function Page() { const data = await fetch(...) }`
- Orval 等の自動生成フック: `useUsersIndex()`, `useUsersStore()` 等

## 特記事項
- page.tsx は薄いラッパーで、実際のビジネスロジックは features/ のコンポーネントにあることが多い
- @/api/ からインポートされるフック名からAPIエンドポイントを推定できる
