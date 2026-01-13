"""LLM utilities - Support for OpenAI and DeepSeek."""

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel

from .config import settings


def get_llm(
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> BaseChatModel:
    """
    Get the LLM instance based on configuration.
    
    Supports:
    - OpenAI (gpt-4o, gpt-4-turbo, etc.)
    - DeepSeek (deepseek-chat, deepseek-coder)
    """
    common_kwargs = {
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    if settings.llm_provider == "openai":
        return ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            **common_kwargs,
        )
    elif settings.llm_provider == "deepseek":
        # DeepSeek uses OpenAI-compatible API
        return ChatOpenAI(
            model=settings.deepseek_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
            **common_kwargs,
        )
    else:
        raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


def get_structured_llm(
    response_schema,
    temperature: float = 0.3,
):
    """
    Get LLM with structured output support.
    
    Args:
        response_schema: Pydantic model for structured output
        temperature: Lower for more deterministic output
    """
    llm = get_llm(temperature=temperature)
    return llm.with_structured_output(response_schema)
