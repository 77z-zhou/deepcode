"""
AskUserQuestion 中间件 - 用于人机交互。

该中间件提供了 AskUserQuestion 工具，允许 Agent
在执行过程中向用户提出结构化问题。
"""

from typing import Optional, Any
from pydantic import BaseModel, Field

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import StructuredTool
from langchain_core.messages import ToolMessage, AIMessage, ToolCall
from langgraph.types import interrupt
from langgraph.runtime import Runtime

from deepcode.core.prompt.tools.ask_user_question import ASK_USER_QUESTION_DESC


# ================ Pydantic 模型定义用于工具输入 Schema ================
class AskUserQuestionOption(BaseModel):
    """A single option within a question."""
    label: str = Field(..., description="The display text for this option that the user will see and select. Should be concise (1-5 words) and clearly describe the choice.")
    description: str = Field(..., description="Explanation of what this option means or what will happen if chosen. Useful for providing context about trade-offs or implications.")
    preview: Optional[str] = Field(None, description="Optional preview content for visual comparisons (single-select only)")


class AskUserQuestionQuestion(BaseModel):
    """A single question to ask the user."""
    question: str = Field(..., description="The complete question to ask the user. Should be clear, specific, and end with a question mark. Example: \"Which library should we use for date formatting?\" If multiSelect is true, phrase it accordingly, e.g. \"Which features do you want to enable?\"")
    header: str = Field(..., description="Very short label displayed as a chip/tag (max 12 chars). Examples: \"Auth method\", \"Library\", \"Approach\".", max_length=12)
    options: list[AskUserQuestionOption] = Field(..., min_length=2, max_length=4, description="The available choices for this question. Must have 2-4 options. Each option should be a distinct, mutually exclusive choice (unless multiSelect is enabled). There should be no 'Other' option, that will be provided automatically.")
    multi_select: bool = Field(False, description="Set to true to allow the user to select multiple options instead of just one. Use when choices are not mutually exclusive.", alias="multiSelect")

    model_config = {"populate_by_name": True}


class AskUserQuestionInput(BaseModel):
    """Input schema for the AskUserQuestion tool."""
    questions: list[AskUserQuestionQuestion] = Field(..., min_length=1, max_length=4, description="Questions to ask the user (1-4 questions)")

#
class AskUserQuestionMiddleware(AgentMiddleware):
    """
    用于在 Agent 执行期间向用户提问的中间件。
    """

    def __init__(self):
        """初始化中间件，创建 AskUserQuestion 工具。"""
        self.tools = [self._create_ask_user_question_tool()]

    def _create_ask_user_question_tool(self) -> StructuredTool:
        def _ask_user_question_fn(input_data: AskUserQuestionInput) -> str:
            return "Questions sent to user. Waiting for response..."

        return StructuredTool.from_function(
            func=_ask_user_question_fn,
            name="AskUserQuestion",
            description=ASK_USER_QUESTION_DESC,
            args_schema=AskUserQuestionInput,
        )

    def _format_answers(self, tool_call: ToolCall, questions: list[dict], answers: dict) -> ToolMessage:
        """
        将用户答案格式化为可读的响应。

        参数:
            questions: 原始问题
            answers: 用户的答案

        返回:
            格式化后的答案字符串
        """
        lines = ["User responses:"]
        lines.append("")

        for q in questions:
            question_text = q.get("question", "")
            header = q.get("header", "")
            answer = answers.get(question_text)

            if answer is None:
                continue

            # 根据答案类型格式化
            if isinstance(answer, list):
                # 多选答案
                selected = ", ".join(answer)
                lines.append(f"**{header}**: {selected}")
            else:
                # 单选答案
                lines.append(f"**{header}**: {answer}")

        tool_msg = ToolMessage(
            name=tool_call['name'],
            tool_call_id=tool_call["id"],
            status="success",
            content="\n".join(lines)
        )
        return tool_msg

    def after_model(self, state, runtime: Runtime):
        """
        模型生成后调用的钩子。

        这里我们拦截 AskUserQuestion 工具调用并处理
        中断/恢复流程。

        参数:
            state: 当前 Agent 状态
            runtime: LangGraph 运行时

        返回:
            如果处理工具调用则返回带 update 的 Command，否则返回 None
        """
        messages = state.get("messages", [])
        if not messages:
            return None

        # 获取最后一条 AI 消息
        last_ai_msg = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None)
        if not last_ai_msg or not last_ai_msg.tool_calls:
            return None
        from langchain.agents.middleware import HumanInTheLoopMiddleware

        # 检查是否有任何工具调用是针对 AskUserQuestion 的
        ask_questions = []
        for tool_call in last_ai_msg.tool_calls:
            tool_name = tool_call.get("name", "")
            if tool_name == "AskUserQuestion":
                tool_args = tool_call.get("args", {})
                questions = tool_args.get("questions", [])
                ask_questions.append(questions)

        if len(ask_questions) == 0: # 不存在 AskUserQuestion 工具调用
            return None

        # 尚无答案 - 准备中断请求数据并触发中断
        hitl_request = {
            "questions": ask_questions,
        }

        # 调用 interrupt() 发送问题给客户端并暂停执行
        # 这个调用会抛出 GraphInterrupt，暂停 agent 执行
        user_answers = interrupt(hitl_request)["user_answers"]

        # 用户回答后，执行恢复到这里
        # 格式化答案并返回 ToolMessage
        artificial_tool_messages = []
        answers_idx = 0
        for tool_call in last_ai_msg.tool_calls:
            tool_name = tool_call.get("name", "")
            if tool_name == "AskUserQuestion":
                questions = ask_questions[answers_idx]
                answers = user_answers[answers_idx]
                tool_msg = self._format_answers(tool_call, questions, answers)
                artificial_tool_messages.append(tool_msg)
                answers_idx += 1
        

        return {"messages": [*artificial_tool_messages]}



    async def aafter_model(self, state, runtime: Runtime):
        """after_model 的异步版本。"""
        return self.after_model(state, runtime)
