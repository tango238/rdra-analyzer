# Nuxt.js (Vue.js / TypeScript)

## 検出条件
- package.json に "nuxt" が含まれる

## プロジェクト構成
- pages/ — ファイルベースルーティング
  - index.vue — / ページ
  - users/index.vue — /users ページ
  - users/[id].vue — /users/:id ページ
- server/api/ — サーバーAPIルート（Nitro）
  - users.get.ts — GET /api/users
  - users.post.ts — POST /api/users
  - users/[id].get.ts — GET /api/users/:id
  - users/[id].put.ts — PUT /api/users/:id
  - users/[id].delete.ts — DELETE /api/users/:id
- components/ — Vueコンポーネント
- composables/ — Composition API ユーティリティ（useXxx 形式）
- stores/ — Pinia ストア（状態管理）
- middleware/ — ルートミドルウェア
- layouts/ — レイアウト
- plugins/ — プラグイン
- nuxt.config.ts — Nuxt設定ファイル

## ルーティング形式
- ファイルシステムベース: pages/ のディレクトリ構造がそのままURLパスになる
- [id] — 動的ルートパラメータ
- [...slug] — キャッチオールルート

## サーバーAPI形式（Nitro）
```typescript
// server/api/users.get.ts
export default defineEventHandler(async (event) => {
    return await User.findAll();
});

// server/api/users/[id].put.ts
export default defineEventHandler(async (event) => {
    const id = getRouterParam(event, 'id');
    const body = await readBody(event);
    return await User.update(id, body);
});
```
- ファイル名の `.get.ts`, `.post.ts` 等でHTTPメソッドを指定

## データ取得パターン
```vue
<script setup>
const { data: users } = await useFetch('/api/users')
const { data: user } = await useAsyncData('user', () => $fetch(`/api/users/${id}`))
</script>
```
