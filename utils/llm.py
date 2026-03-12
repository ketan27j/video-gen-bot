"""
utils/llm.py
Returns the configured LLM instance (Anthropic or OpenAI).
"""

import os
from functools import lru_cache


@lru_cache(maxsize=1)
def get_llm():
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    model = os.getenv("LLM_MODEL", "claude-sonnet-4-5")

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(
            model=model,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            max_tokens=4096,
        )
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=model or "gpt-4o",
            api_key=os.getenv("OPENAI_API_KEY"),
            max_tokens=4096,
        )
    else:
        raise ValueError(f"Unknown LLM_PROVIDER: {provider}. Use 'anthropic' or 'openai'.")