"""Tests for LangChain to OpenAI message format conversion."""

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from app.database.message_adapter import convert_messages_to_standard


def test_convert_system_message():
    """Test SystemMessage conversion."""
    messages = [SystemMessage(content="You are a helpful assistant")]
    result = convert_messages_to_standard(messages)

    assert len(result) == 1
    assert result[0]["role"] == "system"
    assert result[0]["content"] == "You are a helpful assistant"


def test_convert_human_message():
    """Test HumanMessage conversion."""
    messages = [HumanMessage(content="Analyze AAPL")]
    result = convert_messages_to_standard(messages)

    assert len(result) == 1
    assert result[0]["role"] == "user"
    assert result[0]["content"] == "Analyze AAPL"


def test_convert_ai_message_without_tool_calls():
    """Test AIMessage without tool calls."""
    messages = [AIMessage(content="Here is the analysis...")]
    result = convert_messages_to_standard(messages)

    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert result[0]["content"] == "Here is the analysis..."
    assert "tool_calls" not in result[0]


def test_convert_ai_message_with_tool_calls():
    """Test AIMessage with tool calls."""
    messages = [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_abc123",
                    "name": "get_stock_data",
                    "args": {"ticker": "AAPL", "period": "3mo"},
                }
            ],
        )
    ]
    result = convert_messages_to_standard(messages)

    assert len(result) == 1
    assert result[0]["role"] == "assistant"
    assert result[0]["content"] == ""
    assert "tool_calls" in result[0]
    assert len(result[0]["tool_calls"]) == 1

    tool_call = result[0]["tool_calls"][0]
    assert tool_call["id"] == "call_abc123"
    assert tool_call["type"] == "function"
    assert tool_call["function"]["name"] == "get_stock_data"
    assert '"ticker": "AAPL"' in tool_call["function"]["arguments"]


def test_convert_tool_message():
    """Test ToolMessage conversion."""
    messages = [ToolMessage(content='{"price": 150.0}', tool_call_id="call_abc123")]
    result = convert_messages_to_standard(messages)

    assert len(result) == 1
    assert result[0]["role"] == "tool"
    assert result[0]["tool_call_id"] == "call_abc123"
    assert result[0]["content"] == '{"price": 150.0}'


def test_convert_mixed_messages():
    """Test conversion of a complete conversation."""
    messages = [
        SystemMessage(content="You are an analyst"),
        HumanMessage(content="Analyze AAPL"),
        AIMessage(
            content="",
            tool_calls=[{"id": "call_1", "name": "get_stock_data", "args": {"ticker": "AAPL"}}],
        ),
        ToolMessage(content='{"price": 150.0}', tool_call_id="call_1"),
        AIMessage(content="AAPL is trading at $150"),
    ]
    result = convert_messages_to_standard(messages)

    assert len(result) == 5
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    assert result[2]["role"] == "assistant"
    assert "tool_calls" in result[2]
    assert result[3]["role"] == "tool"
    assert result[4]["role"] == "assistant"
