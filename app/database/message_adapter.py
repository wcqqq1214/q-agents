"""Convert LangChain messages to OpenAI standard format."""

from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


def convert_messages_to_standard(messages: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Convert LangChain messages to OpenAI standard format.

    Args:
        messages: List of LangChain BaseMessage objects

    Returns:
        List of dicts in OpenAI message format:
        [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "...", "tool_calls": [...]},
            {"role": "tool", "tool_call_id": "...", "content": "..."}
        ]
    """
    standard_messages = []

    for msg in messages:
        if isinstance(msg, SystemMessage):
            standard_messages.append({"role": "system", "content": msg.content})
        elif isinstance(msg, HumanMessage):
            standard_messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            standard_msg: Dict[str, Any] = {"role": "assistant", "content": msg.content}

            # Handle tool calls if present
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                standard_msg["tool_calls"] = [
                    {
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("name", ""),
                            "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                        },
                    }
                    for tc in tool_calls
                ]

            standard_messages.append(standard_msg)
        elif isinstance(msg, ToolMessage):
            standard_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": msg.tool_call_id,
                    "content": msg.content,
                }
            )
        else:
            # Fallback for unknown message types
            standard_messages.append(
                {
                    "role": "assistant",
                    "content": str(msg.content) if hasattr(msg, "content") else "",
                }
            )

    return standard_messages
