"""
Short-term memory / Session checkpointer for LangGraph Multi-Agent Orchestration.
Maintains state across agent conversations and enables resuming from Human-in-the-Loop interrupts.
"""

from typing import Any
from langgraph.checkpoint.memory import MemorySaver


def get_session_checkpointer() -> Any:
    """
    Returns the checkpointer for conversational thread memory and HITL breakpoints.
    In local/dev environments, uses MemorySaver.
    In cloud environments, this can be swapped with PostgresSaver.
    """
    return MemorySaver()
