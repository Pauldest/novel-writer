"""LLM utilities - Support for OpenAI and DeepSeek."""

import json
import re
from typing import TypeVar

from langchain_openai import ChatOpenAI
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage
from pydantic import BaseModel

from .config import settings


T = TypeVar("T", bound=BaseModel)


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
    response_schema: type[T],
    temperature: float = 0.3,
):
    """
    Get LLM with structured output support.
    
    For OpenAI: Uses native structured output
    For DeepSeek: Returns wrapper that parses JSON manually
    """
    llm = get_llm(temperature=temperature)
    
    if settings.llm_provider == "openai":
        # OpenAI supports native structured output
        return llm.with_structured_output(response_schema)
    else:
        # DeepSeek doesn't support structured output, use JSON parsing wrapper
        return DeepSeekStructuredLLM(llm, response_schema)


class DeepSeekStructuredLLM:
    """
    Wrapper for DeepSeek that manually parses JSON responses.
    
    Since DeepSeek doesn't support response_format, we:
    1. Add JSON schema to the prompt
    2. Parse the JSON from the response
    """
    
    def __init__(self, llm: BaseChatModel, response_schema: type[T]):
        self.llm = llm
        self.response_schema = response_schema
    
    def invoke(self, messages: list) -> T:
        """Invoke LLM and parse structured response."""
        # Add JSON format instruction to the last message
        schema_json = self.response_schema.model_json_schema()
        format_instruction = f"""

请严格按照以下JSON格式返回响应，不要包含任何其他文字说明：

```json
{json.dumps(schema_json, ensure_ascii=False, indent=2)}
```

只返回JSON对象，不要有任何前缀或后缀文字。"""
        
        # Modify the last human message to include format instruction
        modified_messages = list(messages)
        if modified_messages and hasattr(modified_messages[-1], 'content'):
            modified_messages[-1] = HumanMessage(
                content=modified_messages[-1].content + format_instruction
            )
        
        # Call LLM
        response = self.llm.invoke(modified_messages)
        content = response.content
        
        # Extract JSON from response
        json_str = self._extract_json(content)
        
        # Parse and validate
        try:
            data = json.loads(json_str)
            return self.response_schema.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            # If parsing fails, try to be more aggressive about extraction
            raise ValueError(f"Failed to parse LLM response as JSON: {e}\nResponse: {content}")
    
    def _extract_json(self, text: str) -> str:
        """Extract JSON from text, handling markdown code blocks."""
        # Try to find JSON in code block
        code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', text)
        if code_block_match:
            return code_block_match.group(1).strip()
        
        # Try to find raw JSON object
        json_match = re.search(r'\{[\s\S]*\}', text)
        if json_match:
            return json_match.group(0)
        
        # Return as-is and hope for the best
        return text.strip()
