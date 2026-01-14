"""Base Agent class - Foundation for all agents."""

from abc import ABC, abstractmethod
from typing import Any, TypeVar, Generic
from pydantic import BaseModel

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage, HumanMessage

from ..llm import get_llm, get_structured_llm


T = TypeVar("T", bound=BaseModel)


class BaseAgent(ABC, Generic[T]):
    """
    基础 Agent 类 - 所有 Agent 的父类。
    
    特性：
    - 统一的 LLM 调用接口
    - 支持结构化输出
    - 可配置的 system prompt
    """
    
    def __init__(
        self,
        system_prompt: str,
        response_schema: type[T] | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        """
        Initialize base agent.
        
        Args:
            system_prompt: System prompt defining agent behavior
            response_schema: Pydantic model for structured output (optional)
            temperature: LLM temperature
            max_tokens: Maximum output tokens
        """
        self.system_prompt = system_prompt
        self.response_schema = response_schema
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Initialize LLM
        if response_schema:
            self._llm = get_structured_llm(response_schema, temperature=temperature)
        else:
            self._llm = get_llm(temperature=temperature, max_tokens=max_tokens)
    
    def get_format_instruction(self) -> str:
        """Get hidden format instruction from LLM if valid."""
        if hasattr(self._llm, "get_format_instruction"):
            return self._llm.get_format_instruction()
        return ""
    
    def invoke(self, user_input: str, **kwargs) -> T | str:
        """
        Invoke the agent with user input.
        
        Args:
            user_input: The user's input/request
            **kwargs: Additional context to inject into the prompt
            
        Returns:
            Structured response (if schema provided) or string
        """
        # Build messages
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_input),
        ]
        
        # Invoke LLM
        response = self._llm.invoke(messages)
        
        # Return appropriate type
        if self.response_schema:
            return response  # Already parsed by structured output
        return response.content
    
    @abstractmethod
    def run(self, **kwargs) -> Any:
        """
        Run the agent's main task.
        
        This method should be implemented by subclasses to define
        the agent's specific behavior.
        """
        pass
