"""
LLMプロバイダーパッケージ

環境変数 USE_CLAUDE_CODE=true で claude CLI サブプロセスを使用、
デフォルトは Anthropic API を直接呼び出す。
"""

from .provider import LLMProvider, LLMMessage, LLMResponse
from .anthropic_provider import AnthropicProvider
from .claude_code_provider import ClaudeCodeProvider


def get_provider() -> LLMProvider:
    """
    環境変数に基づいて適切なLLMプロバイダーを返す。

    USE_CLAUDE_CODE=true の場合: Claude CLIサブプロセスを使用
    デフォルト: Anthropic API を直接使用
    """
    from config import get_config
    config = get_config()

    if config.use_claude_code:
        return ClaudeCodeProvider()
    else:
        return AnthropicProvider(
            api_key=config.anthropic_api_key,
            model=config.claude_model,
        )


__all__ = [
    "LLMProvider",
    "LLMMessage",
    "LLMResponse",
    "AnthropicProvider",
    "ClaudeCodeProvider",
    "get_provider",
]
