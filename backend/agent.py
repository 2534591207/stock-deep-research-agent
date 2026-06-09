"""agent.py — Build the two-layer US stock research ReAct agent.

Uses LangGraph's create_react_agent (pre-built ReAct loop) with:
- ChatOpenAI as the LLM backbone
- MemorySaver as the in-memory session checkpointer (thread_id = session_id)
- Tools: analyze_stocks, generate_report, analyze_document, find_news
- SYSTEM_PROMPT as the persona / routing instruction
"""
from __future__ import annotations

import warnings
from typing import Any, Optional

# Suppress LangGraph deprecation warning about create_react_agent location
warnings.filterwarnings(
    "ignore",
    message="create_react_agent has been moved",
    category=DeprecationWarning,
)

from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

from langchain_openai import ChatOpenAI

from config import settings
from prompts import SYSTEM_PROMPT
from tools import analyze_document, analyze_stocks, find_news, generate_report


# ---------------------------------------------------------------------------
# Module-level singleton (created lazily on first call)
# ---------------------------------------------------------------------------

_agent_instance: Any = None


def build_agent(model: Optional[Any] = None) -> Any:
    """Build (or return the cached) ReAct agent.

    Args:
        model: Optional LangChain chat model. Defaults to ChatOpenAI using
               settings.openai_model (gpt-4o-mini). Inject a fake model for
               offline / unit tests.

    Returns:
        A compiled LangGraph agent (CompiledStateGraph).
    """
    global _agent_instance

    if model is not None:
        # When a custom model is injected (e.g. in tests), always build fresh.
        return _build(model)

    if _agent_instance is None:
        _agent_instance = _build(
            ChatOpenAI(
                model=settings.openai_model,
                temperature=0,
                # Enable token-by-token streaming so /chat/stream can forward
                # on_llm_new_token callbacks. The synchronous /chat path collects
                # the full reply from the final message regardless, so this is a
                # no-op for /chat behaviour (only the transport differs).
                streaming=True,
                api_key=settings.openai_api_key,  # pydantic-settings 读 .env，不进 os.environ，须显式传
                # Disable OpenAI parallel tool-calling so the model emits at most ONE
                # tool call per assistant turn. This forces a single generate_report
                # call carrying ALL requested stocks (companies=[...]), preserving the
                # cross-stock Relative Rank instead of fanning out into per-stock calls.
                # langchain-openai 1.2.2 has no first-class parallel_tool_calls field,
                # so it must be passed via model_kwargs; create_react_agent's internal
                # bind_tools preserves it and it flows into the API request payload.
                model_kwargs={"parallel_tool_calls": False},
            )
        )
    return _agent_instance


def reset_agent() -> None:
    """Reset the cached singleton (useful between tests)."""
    global _agent_instance
    _agent_instance = None


def _build(model: Any) -> Any:
    """Internal: construct a fresh agent with the given model."""
    checkpointer = MemorySaver()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        agent = create_react_agent(
            model,
            tools=[analyze_stocks, generate_report, analyze_document, find_news],
            checkpointer=checkpointer,
            prompt=SYSTEM_PROMPT,
        )
    return agent
