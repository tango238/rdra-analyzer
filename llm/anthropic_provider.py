"""
Anthropic API 直接呼び出し実装

ANTHROPIC_API_KEY 環境変数を使用して Anthropic の API を直接呼び出す。
USE_CLAUDE_CODE=false（デフォルト）の場合に使用される。
"""

import anthropic
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .provider import LLMProvider, LLMMessage, LLMResponse


class AnthropicProvider(LLMProvider):
    """
    Anthropic API を直接呼び出すプロバイダー。

    本番環境やCI/CD環境での使用を想定している。
    APIキーが必要。
    """

    def __init__(self, api_key: str, model: str = "claude-opus-4-5"):
        """
        Args:
            api_key: Anthropic APIキー（ANTHROPIC_API_KEY）
            model: 使用するモデル名
        """
        if not api_key:
            raise ValueError(
                "Anthropic APIキーが指定されていません。"
                "ANTHROPIC_API_KEY環境変数を設定してください。"
            )
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    @retry(
        # APIレート制限やネットワークエラー時にリトライ
        retry=retry_if_exception_type((anthropic.RateLimitError, anthropic.APIConnectionError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60),
    )
    def complete(
        self,
        messages: list[LLMMessage],
        system_prompt: str = "",
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> LLMResponse:
        """
        Anthropic API を呼び出してレスポンスを取得する。

        Args:
            messages: メッセージ履歴
            system_prompt: システムプロンプト
            max_tokens: 最大出力トークン数
            temperature: サンプリング温度

        Returns:
            LLMResponse: Anthropic APIのレスポンス
        """
        # メッセージを Anthropic API 形式に変換
        api_messages = [
            {"role": msg.role, "content": msg.content}
            for msg in messages
        ]

        # API呼び出し（システムプロンプトは存在する場合のみ設定）
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        response = self._client.messages.create(**kwargs)

        # レスポンスを共通形式に変換
        return LLMResponse(
            content=response.content[0].text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            stop_reason=response.stop_reason or "end_turn",
        )

    @property
    def provider_name(self) -> str:
        return "anthropic"

    @property
    def model_name(self) -> str:
        return self._model
