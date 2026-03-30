"""
設定・環境変数管理モジュール

環境変数で動作を切り替える:
  USE_CLAUDE_CODE=true  → claude CLIサブプロセス呼び出し（ローカル実行用）
  デフォルト            → Anthropic API直接呼び出し
"""

import os
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class Config:
    # ===== LLMプロバイダー設定 =====
    # trueの場合はclaude CLIサブプロセスを使用
    use_claude_code: bool = field(
        default_factory=lambda: os.environ.get("USE_CLAUDE_CODE", "false").lower() == "true"
    )
    # Anthropic APIキー（USE_CLAUDE_CODE=falseの場合に必要）
    anthropic_api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    # 使用するClaudeモデル
    claude_model: str = field(
        default_factory=lambda: os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")
    )
    # APIタイムアウト（秒）
    api_timeout: int = field(
        default_factory=lambda: int(os.environ.get("API_TIMEOUT", "120"))
    )

    # ===== Claude CLI設定 =====
    # claude CLI のマルチターン上限
    CLAUDE_MAX_TURNS: int = field(
        default_factory=lambda: int(os.environ.get("CLAUDE_MAX_TURNS", "100"))
    )
    # claude CLI で使用するモデル（claude_model と共用）
    CLAUDE_MODEL: str = field(
        default_factory=lambda: os.environ.get("CLAUDE_MODEL", "claude-opus-4-5")
    )
    # claude CLI に許可するツール（カンマ区切り）
    CLAUDE_ALLOWED_TOOLS: str = field(
        default_factory=lambda: os.environ.get("CLAUDE_ALLOWED_TOOLS", "Read,Glob,Grep,Bash")
    )
    # analyze_codebase のタイムアウト（秒）
    CLAUDE_ANALYZE_TIMEOUT: int = field(
        default_factory=lambda: int(os.environ.get("CLAUDE_ANALYZE_TIMEOUT", "600"))
    )

    # ===== リポジトリパス設定 =====
    # 解析対象リポジトリパス（カンマ区切りで複数指定可）
    repo_paths: list[Path] = field(
        default_factory=lambda: [
            Path(p.strip())
            for p in os.environ.get("REPO_PATHS", "").split(",")
            if p.strip()
        ]
    )

    # ===== プロジェクトコンテキスト設定 =====
    # コンテキストとして読み込むファイル名
    project_context_files: list[str] = field(
        default_factory=lambda: [
            f.strip()
            for f in os.environ.get(
                "PROJECT_CONTEXT_FILES", "CLAUDE.md,AGENTS.md,README.md"
            ).split(",")
        ]
    )

    # ===== 出力設定 =====
    # 解析結果の出力ディレクトリ
    output_dir: Path = field(
        default_factory=lambda: Path(
            os.environ.get("OUTPUT_DIR", "./output")
        )
    )

    # ===== E2E設定 =====
    # テスト対象のベースURL
    e2e_base_url: str = field(
        default_factory=lambda: os.environ.get("E2E_BASE_URL", "http://localhost:3000")
    )
    # ヘッドレスモード
    e2e_headless: bool = field(
        default_factory=lambda: os.environ.get("E2E_HEADLESS", "true").lower() == "true"
    )
    # スクリーンショット保存ディレクトリ
    e2e_screenshot_dir: str = "output/e2e/screenshots"
    # シナリオ実行タイムアウト（ミリ秒）
    e2e_timeout_ms: int = field(
        default_factory=lambda: int(os.environ.get("E2E_TIMEOUT_MS", "30000"))
    )
    # エラー時の最大リトライ回数
    e2e_max_retries: int = field(
        default_factory=lambda: int(os.environ.get("E2E_MAX_RETRIES", "3"))
    )
    # テストユーザーのメールアドレス
    e2e_test_email: str = field(
        default_factory=lambda: os.environ.get("E2E_TEST_EMAIL", "test@example.com")
    )
    # テストユーザーのパスワード
    e2e_test_password: str = field(
        default_factory=lambda: os.environ.get("E2E_TEST_PASSWORD", "password")
    )

    def validate(self) -> None:
        """設定値の検証"""
        if not self.use_claude_code and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEYが設定されていません。"
                "USE_CLAUDE_CODE=trueを設定するか、ANTHROPIC_API_KEYを設定してください。"
            )
        if not self.repo_paths:
            raise ValueError(
                "解析対象リポジトリが指定されていません。"
                "REPO_PATHS環境変数またはCLIの --repo オプションで指定してください。"
            )
        for repo_path in self.repo_paths:
            if not repo_path.exists():
                raise ValueError(f"リポジトリパスが存在しません: {repo_path}")

    def ensure_output_dirs(self) -> None:
        """出力ディレクトリを作成"""
        for subdir in ["usecases", "rdra", "gap", "e2e", "e2e/screenshots"]:
            (self.output_dir / subdir).mkdir(parents=True, exist_ok=True)


# グローバル設定インスタンス
_config: Config | None = None


def get_config() -> Config:
    """設定シングルトンを取得"""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reset_config() -> None:
    """テスト用: 設定をリセット"""
    global _config
    _config = None
