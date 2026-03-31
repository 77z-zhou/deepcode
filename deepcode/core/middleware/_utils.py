import math

from typing import Sequence, Literal

from langchain_core.messages import (
    ContentBlock, 
    SystemMessage, 
    AnyMessage,
    AIMessage,
    ToolMessage,
    BaseMessage,
    HumanMessage,
)

def get_buffer_string(
    messages: Sequence[BaseMessage],
    human_prefix: str = "Human",
    ai_prefix: str = "AI",
    *,
    system_prefix: str = "System",
    tool_prefix: str = "Tool",
    message_separator: str = "\n"
) -> str:
    string_messages = []
    for m in messages:
        if isinstance(m, HumanMessage):
            role = human_prefix
        elif isinstance(m, AIMessage):
            role = ai_prefix
        elif isinstance(m, SystemMessage):
            role = system_prefix
        elif isinstance(m, ToolMessage):
            role = tool_prefix
        else:
            msg = f"Got unsupported message type: {m}"
            raise ValueError(msg)
        
        content = m.text
        message = f"{role}: {content}"
        tool_info = ""
        if isinstance(m, AIMessage):
            if m.tool_calls:
                tool_info = str(m.tool_calls)
            elif "function_call" in m.additional_kwargs:
                tool_info = str(m.additional_kwargs["function_call"])
        if tool_info:
            message += tool_info 

        string_messages.append(message)
    return message_separator.join(string_messages)


def count_tokens_approximately(
    messages: list[AnyMessage], 
    *, 
    chars_per_token: float = 4.0,
    extra_tokens_per_message: float = 3.0,
    tokens_per_image: int = 85
):
    
    token_count = 0.0
    for message in messages:
        message_chars = 0
        if isinstance(message.content, str):
            message_chars += len(message.content)
        elif isinstance(message.content, list):
            for block in message.content:
                if isinstance(block, str):
                    message_chars += len(block)
                elif isinstance(block, dict):
                    block_type = block.get("type", "")
                    if block_type in {"image", "image_url"}:
                        token_count += tokens_per_image
                    elif block_type == "text":
                        text = block.get("text", "")
                        message_chars += len(text)
                    else:
                        message_chars += len(repr(block))
                else:
                    # Fallback for unexpected block types
                    message_chars += len(repr(block))
        else:
            # Fallback for other content types
            content = repr(message.content)
            message_chars += len(content)
        if (
            isinstance(message, AIMessage)
            # exclude Anthropic format as tool calls are already included in the content
            and not isinstance(message.content, list)
            and message.tool_calls
        ):
            tool_calls_content = repr(message.tool_calls)
            message_chars += len(tool_calls_content)

        if isinstance(message, ToolMessage):
            message_chars += len(message.tool_call_id)

        role = _get_message_openai_role(message)
        message_chars += len(role)

        token_count += math.ceil(message_chars / chars_per_token)
        token_count += extra_tokens_per_message
    return math.ceil(token_count)

def _get_message_openai_role(message: BaseMessage) -> str:
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, ToolMessage):
        return "tool"
    if isinstance(message, SystemMessage):
        role = message.additional_kwargs.get("__openai_role__", "system")
        if not isinstance(role, str):
            msg = f"Expected '__openai_role__' to be a str, got {type(role).__name__}"
            raise TypeError(msg)
        return role
    msg = f"Unknown BaseMessage type {message.__class__}."
    raise ValueError(msg)

def append_to_system_message(
    system_message: SystemMessage | None,
    text: str,
) -> SystemMessage:
    new_content: list[ContentBlock] = list(system_message.content_blocks) if system_message else []
    if new_content:
        text = f"\n\n{text}"
    new_content.append({"type": "text", "text": text})
    return SystemMessage(content_blocks=new_content)
