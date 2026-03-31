import time
import uuid
import json
from typing import Any
from pathlib import Path

from langchain.chat_models import BaseChatModel
from langchain.agents.middleware import AgentMiddleware, SummarizationMiddleware
from langchain.agents import AgentState
from langchain.messages import AnyMessage, ToolMessage, HumanMessage, RemoveMessage, AIMessage

from langgraph.graph.message import (
    REMOVE_ALL_MESSAGES,
)

from ._utils import count_tokens_approximately, get_buffer_string


KEEP_TOOL_RECENT = 3
KEEP_MESSAGE_RECENT = 8
TRANS_THRESHOLD = 50000

SUMMARIZE_PROMPT = """Summarize this conversation for continuity. Include: 
1) What was accomplished, 2) Current state, 3) Key decisions made. 
Be concise but preserve critical details.\n\n
<conversion>{conversion}</conversion>
"""

class ContextCompactMiddleware(AgentMiddleware):
    """ context compact """
    def __init__(
        self,
        summarize_model: BaseChatModel,
        transcript_dir: Path,
        keep_tool_recent: int = KEEP_TOOL_RECENT,
        keep_message_recent: int = KEEP_MESSAGE_RECENT,
        trans_threshold: int = TRANS_THRESHOLD
    ):
        self.summarize_model = summarize_model
        self.transcript_dir = transcript_dir
        self.keep_tool_recent = keep_tool_recent
        self.keep_message_recent = keep_message_recent
        self.trans_threshold = trans_threshold

    
    def before_model(self, state: AgentState[Any], runtime):
        messages = state['messages']
        self._ensure_message_ids(messages)
        
        # 1. mirco compact - replace old tool results with placeholders
        messages = self.mirco_compact(messages)

        # 2. auto compact - save transcript, summarize, replace messages
        if count_tokens_approximately(messages) > self.trans_threshold:
            cut_off_messages = messages[:-self.keep_message_recent]
            preserved_messages = messages[-self.keep_message_recent:]
            # save transcript
            transcript_path = self.save_transcript(cut_off_messages)
            # summarize
            summary = self.summarize_conversion(cut_off_messages)
            new_messages = self._build_new_messages(summary, preserved_messages, transcript_path)
        else:
            new_messages = messages

        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *new_messages,
            ]
        }
    
    async def abefore_model(self, state, runtime):
        messages = state['messages']
        self._ensure_message_ids(messages)
        
        # 1. mirco compact - replace old tool results with placeholders
        messages = self.mirco_compact(messages)

        # 2. auto compact - save transcript, summarize, replace messages
        if count_tokens_approximately(messages) > self.trans_threshold:
            cut_off_messages = messages[:-self.keep_message_recent]
            preserved_messages = messages[-self.keep_message_recent:]
            # save transcript
            transcript_path = self.save_transcript(cut_off_messages)
            # summarize
            summary = await self.asummarize_conversion(cut_off_messages)
            new_messages = self._build_new_messages(summary, preserved_messages, transcript_path)
        else:
            new_messages = messages

        return {
            "messages": [
                RemoveMessage(id=REMOVE_ALL_MESSAGES),
                *new_messages,
            ]
        }
    
    def save_transcript(self, messages: list[AnyMessage]):
        # save full transcript to disk
        self.transcript_dir.mkdir(exist_ok=True)
        transcript_path = self.transcript_dir / f"transcript_{int(time.time())}.jsonl"
        with open(transcript_path, "w") as f:
            for msg in messages:
                f.write(json.dumps(msg, default=str) + "\n")
        return str(transcript_path)

    def summarize_conversion(self, messages: list[AnyMessage]):
        # ask llm to summarize
        conversation_text = get_buffer_string(messages)
        prompt = SUMMARIZE_PROMPT.format(conversion=conversation_text)
        try:
            response = self.summarize_model.invoke(prompt, config={"metadata": {"lc_source": "summarization"}})
            return response.text.strip()
        except Exception as e:
            return f"Error generating summary: {e!s}"
        
    async def asummarize_conversion(self, messages: list[AnyMessage]):
        conversation_text = get_buffer_string(messages)
        prompt = SUMMARIZE_PROMPT.format(conversion=conversation_text)
        try:
            response = await self.summarize_model.ainvoke(prompt, config={"metadata": {"lc_source": "summarization"}})
            return response.text.strip()
        except Exception as e:
            return f"Error generating summary: {e!s}" 

        

    def mirco_compact(self, messages: list[AnyMessage]):
        tool_msgs: list[ToolMessage] = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                tool_msgs.append(msg)
    
        if len(tool_msgs) <= self.keep_tool_recent:
            return messages
        
        to_clear = tool_msgs[:-self.keep_tool_recent]
        for msg in to_clear:
            msg.content = f"[Previous: used {msg.name}]"
        return messages


    def _ensure_message_ids(self,messages: list[AnyMessage]) -> None:
        for msg in messages:
            if msg.id is None:
                msg.id = str(uuid.uuid4())

    def _build_new_messages(self, summary: str, preserved_messages: list[AnyMessage], transcript_path: str) -> list[AnyMessage]:
        return [
            HumanMessage(
                content=f"[Conversion compressed. Transcript: {transcript_path}]\nHere is a summary of the conversation to date:\n\n{summary}",
                additional_kwargs={"lc_source": "summarization"},
            ),
            AIMessage(content="Understood. I have the context from the summary. Continuing."),
            *preserved_messages,
        ]