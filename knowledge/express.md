# Express.js (Node.js / TypeScript)

## 検出条件
- package.json に "express" が含まれる

## プロジェクト構成
- src/app.ts または app.js — アプリケーションエントリーポイント
- src/routes/ — ルーター定義
- src/controllers/ — コントローラー
- src/models/ — モデル（Sequelize / TypeORM / Prisma）
- src/middleware/ — ミドルウェア
- src/services/ — サービス層
- prisma/schema.prisma — Prismaスキーマ（Prisma使用時）
- src/entities/ — TypeORMエンティティ（TypeORM使用時）

## ルーティング形式
```typescript
import { Router } from 'express';
const router = Router();

router.get('/users', userController.list);
router.get('/users/:id', userController.show);
router.post('/users', userController.create);
router.put('/users/:id', userController.update);
router.delete('/users/:id', userController.destroy);

// app.ts
app.use('/api/v1', router);
```
- Router() でルーターを作成、app.use() でマウント
- :id でパスパラメータ

## モデル形式（Prisma）
```prisma
model User {
  id        Int      @id @default(autoincrement())
  name      String
  email     String   @unique
  posts     Post[]
  company   Company  @relation(fields: [companyId], references: [id])
  companyId Int
}
```

## モデル形式（TypeORM）
```typescript
@Entity()
export class User {
    @PrimaryGeneratedColumn()
    id: number;

    @Column()
    name: string;

    @OneToMany(() => Post, post => post.user)
    posts: Post[];

    @ManyToOne(() => Company)
    company: Company;
}
```

## モデル形式（Sequelize）
```typescript
class User extends Model {
    declare id: number;
    declare name: string;
    static associate(models) {
        User.hasMany(models.Post);
        User.belongsTo(models.Company);
    }
}
```
