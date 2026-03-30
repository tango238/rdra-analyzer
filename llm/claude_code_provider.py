"""
Claude Code CLI サブプロセス呼び出し実装

`claude` コマンドをサブプロセスとして実行する。
USE_CLAUDE_CODE=true の場合に使用される。
ローカル環境でAPIキーなしに実行できる。
"""

import json
import subprocess
import shutil
from pathlib import Path

from .provider import LLMProvider, LLMMessage, LLMResponse


class ClaudeCodeProvider(LLMProvider):
    """
    Claude Code CLI (claude コマンド) をサブプロセスで呼び出すプロバイダー。

    ローカル開発環境での使用を想定している。
    `claude` コマンドがインストールされていてログイン済みである必要がある。

    実行例:
        echo "メッセージ" | claude --output-format json --model claude-opus-4-5
    """

    def __init__(self, model: str | None = None):
        """
        Args:
            model: 使用するモデル名
        """
        # claude CLI が利用可能か確認
        if not shutil.which("claude"):
            raise RuntimeError(
                "claude コマンドが見つかりません。"
                "Claude Code CLI をインストールしてログインしてください: "
                "https://claude.ai/code"
            )
        # モデル未指定時は config から取得
        if model is None:
            from config import get_config
            cfg = get_config()
            model = cfg.CLAUDE_MODEL
        self._model = model

        # config から CLI 設定を読み込む
        from config import get_config
        _cfg = get_config()
        self._max_turns: int = _cfg.CLAUDE_MAX_TURNS
        self._allowed_tools: str = _cfg.CLAUDE_ALLOWED_TOOLS
        self._analyze_timeout: int = _cfg.CLAUDE_ANALYZE_TIMEOUT

    def complete(
        self,
        messages: list[LLMMessage],
        system_prompt: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """
        claude CLI をサブプロセスとして実行してレスポンスを取得する。

        claude CLI は標準入力からプロンプトを受け取り、
        --output-format json で JSON形式のレスポンスを返す。

        Args:
            messages: メッセージ履歴
            system_prompt: システムプロンプト
            max_tokens: 最大出力トークン数（CLIでは無視される場合あり）
            temperature: サンプリング温度（CLIでは無視される場合あり）

        Returns:
            LLMResponse: CLIのレスポンス
        """
        # メッセージを一つのテキストにまとめる
        # Claude Code CLI はシンプルなプロンプトを期待している
        prompt_parts = []

        # システムプロンプトをプロンプト冒頭に追加
        if system_prompt:
            prompt_parts.append(f"<system>\n{system_prompt}\n</system>\n")

        # 会話履歴を追加
        for msg in messages:
            if msg.role == "user":
                prompt_parts.append(f"Human: {msg.content}")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {msg.content}")

        full_prompt = "\n\n".join(prompt_parts)

        # claude CLI コマンドを構築
        cmd = [
            "claude",
            "--output-format", "json",
            "--model", self._model,
            "--print",          # 非インタラクティブモード
        ]

        try:
            # サブプロセスとして claude を実行
            result = subprocess.run(
                cmd,
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=300,  # 5分タイムアウト
                encoding="utf-8",
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"claude CLI がエラーで終了しました (code={result.returncode}):\n"
                    f"stderr: {result.stderr}"
                )

            # JSON出力をパース
            output = result.stdout.strip()
            response_text = self._parse_cli_output(output)

            return LLMResponse(
                content=response_text,
                model=self._model,
                stop_reason="end_turn",
            )

        except subprocess.TimeoutExpired:
            raise RuntimeError("claude CLI の実行がタイムアウトしました（300秒）")

    def _parse_cli_output(self, output: str) -> str:
        """
        claude CLI の出力をパースしてテキストを抽出する。

        JSON形式の場合はパース、それ以外はそのまま返す。

        Args:
            output: claude CLI の標準出力

        Returns:
            str: 抽出されたテキスト
        """
        if not output:
            return ""

        # JSON形式での出力を試みる
        try:
            data = json.loads(output)

            # claude CLI の --output-format json は JSON配列を返す場合がある
            if isinstance(data, list):
                # 配列の場合、result アイテムを探す
                for item in data:
                    if isinstance(item, dict) and item.get("type") == "result":
                        result_text = item.get("result", "")
                        if result_text:
                            return str(result_text)
                # result がなければ assistant の text ブロックを集める
                texts = []
                for item in data:
                    if isinstance(item, dict) and item.get("type") == "assistant":
                        for block in item.get("message", {}).get("content", []):
                            if isinstance(block, dict) and block.get("type") == "text":
                                texts.append(block["text"])
                if texts:
                    return texts[-1]  # 最後のテキストブロックを返す

            # dict の場合
            if isinstance(data, dict):
                if "result" in data:
                    return str(data["result"])
                if "content" in data:
                    content = data["content"]
                    if isinstance(content, list):
                        texts = [
                            block.get("text", "")
                            for block in content
                            if isinstance(block, dict) and block.get("type") == "text"
                        ]
                        return "\n".join(texts)
                    return str(content)
        except json.JSONDecodeError:
            pass

        # JSON でない場合はそのまま返す
        return output

    def analyze_codebase(
        self,
        path: str,
        prompt: str,
        timeout: int = 600,
    ) -> str:
        """
        Claude CLI を使ってコードベースを自律的に探索・解析する。

        --allowedTools "Read,Glob,Grep,Bash" を指定して、ファイルシステムツールを
        使いながら最大20ターンで自律的にコードを探索させる。

        Args:
            path: 解析対象ディレクトリの絶対パス
            prompt: 解析指示プロンプト
            timeout: タイムアウト秒数（デフォルト600秒=10分）

        Returns:
            str: Claude の解析結果テキスト（JSON を含む）
        """
        effective_timeout = timeout if timeout != 600 else self._analyze_timeout
        cmd = [
            "claude",
            "--output-format", "json",
            "--model", self._model,
            "--print",
            "--allowedTools", self._allowed_tools,
            "--max-turns", str(self._max_turns),
        ]

        try:
            result = subprocess.run(
                cmd,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=effective_timeout,
                encoding="utf-8",
                cwd=path,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"claude CLI がエラーで終了しました (code={result.returncode}):\n"
                    f"stderr: {result.stderr[:500]}"
                )

            output = result.stdout.strip()
            return self._parse_cli_output(output)

        except subprocess.TimeoutExpired:
            raise RuntimeError(f"claude CLI の実行がタイムアウトしました（{effective_timeout}秒）")

    @property
    def provider_name(self) -> str:
        return "claude_code"

    @property
    def model_name(self) -> str:
        return self._model
