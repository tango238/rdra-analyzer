"""
LLMProvider 抽象基底クラス

Anthropic API と Claude Code CLI の両方に対応するインターフェースを定義する。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class LLMMessage:
    """LLMへのメッセージ"""
    role: str           # "user" または "assistant"
    content: str        # メッセージ内容


@dataclass
class LLMResponse:
    """LLMからのレスポンス"""
    content: str                        # レスポンステキスト
    input_tokens: int = 0               # 入力トークン数
    output_tokens: int = 0              # 出力トークン数
    model: str = ""                     # 使用したモデル名
    stop_reason: str = "end_turn"       # 停止理由


class LLMProvider(ABC):
    """
    LLMプロバイダーの抽象基底クラス。

    このクラスを継承して以下の2つの実装を提供する:
    - AnthropicProvider: Anthropic API を直接呼び出す
    - ClaudeCodeProvider: claude CLI をサブプロセスで呼び出す
    """

    @abstractmethod
    def complete(
        self,
        messages: list[LLMMessage],
        system_prompt: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """
        LLMにメッセージを送信してレスポンスを取得する。

        Args:
            messages: メッセージ履歴（role と content のリスト）
            system_prompt: システムプロンプト（任意）
            max_tokens: 最大出力トークン数
            temperature: サンプリング温度（0.0〜1.0）

        Returns:
            LLMResponse: レスポンスオブジェクト
        """
        ...

    def complete_simple(
        self,
        user_message: str,
        system_prompt: str = "",
        max_tokens: int = 8192,
    ) -> str:
        """
        シンプルな単発メッセージを送信してテキストを取得する。

        Args:
            user_message: ユーザーメッセージ
            system_prompt: システムプロンプト（任意）
            max_tokens: 最大出力トークン数

        Returns:
            str: レスポンステキスト
        """
        response = self.complete(
            messages=[LLMMessage(role="user", content=user_message)],
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )
        return response.content

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """プロバイダー名を返す"""
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """使用しているモデル名を返す"""
        ...
