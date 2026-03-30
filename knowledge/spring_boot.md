# Spring Boot (Java / Kotlin)

## 検出条件
- pom.xml に "spring-boot" が含まれる
- build.gradle / build.gradle.kts に "spring-boot" が含まれる

## プロジェクト構成
- src/main/java/<package>/
  - Application.java — エントリーポイント（@SpringBootApplication）
  - controller/ — RESTコントローラー
  - service/ — サービス層
  - repository/ — リポジトリ（データアクセス）
  - model/ または entity/ — JPAエンティティ
  - dto/ — DTOクラス
  - config/ — 設定クラス
- src/main/resources/
  - application.yml / application.properties — 設定ファイル
- src/test/java/ — テスト

## ルーティング形式
```java
@RestController
@RequestMapping("/api/v1/users")
public class UserController {
    @GetMapping
    public List<UserDto> listUsers() { ... }

    @GetMapping("/{id}")
    public UserDto getUser(@PathVariable Long id) { ... }

    @PostMapping
    public UserDto createUser(@RequestBody @Valid UserCreateDto dto) { ... }

    @PutMapping("/{id}")
    public UserDto updateUser(@PathVariable Long id, @RequestBody UserUpdateDto dto) { ... }

    @DeleteMapping("/{id}")
    public void deleteUser(@PathVariable Long id) { ... }
}
```
- @RequestMapping でベースパスを定義
- @GetMapping, @PostMapping, @PutMapping, @DeleteMapping でHTTPメソッド別にマッピング
- @PathVariable でURLパスパラメータ、@RequestBody でリクエストボディをバインド

## モデル形式（JPA）
```java
@Entity
@Table(name = "users")
public class User {
    @Id @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String name;

    @OneToMany(mappedBy = "user", cascade = CascadeType.ALL)
    private List<Post> posts;

    @ManyToOne
    @JoinColumn(name = "company_id")
    private Company company;
}
```
- リレーション: @OneToMany, @ManyToOne, @OneToOne, @ManyToMany
- @Table でテーブル名指定、@Column でカラム制約

## リポジトリ形式
```java
public interface UserRepository extends JpaRepository<User, Long> {
    List<User> findByNameContaining(String name);
    Optional<User> findByEmail(String email);
}
```
