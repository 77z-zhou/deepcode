from typing import Callable

from langgraph.types import Command

from langchain.agents import create_agent
from langchain.agents.middleware.human_in_the_loop import HITLRequest
from langchain.agents.middleware import HumanInTheLoopMiddleware

from langgraph.types import Interrupt
from langgraph.checkpoint.memory import MemorySaver

from deepcode.core.model import create_model
from deepcode.config.settings import Settings
from deepcode.core.middleware.optsystem import OptSystemMiddleware
from deepcode.core.middleware.todo import TodoListMiddleware
from deepcode.core.middleware.skills import SkillsMiddelware
from deepcode.core.middleware.ask_user_question import AskUserQuestionMiddleware


# from deepcode.core.middleware.compact import ContextCompactMiddleware
# from deepcode.core.middleware.subagent import SubAgentMiddleware

# SYSTEM = f"""You are a coding agent at {WORKDIR}. Use tools to solve tasks.
# Prefer task_create/task_update/task_list for multi-step work. Use TodoWrite for short checklists.
# Use task for subagent delegation. Use load_skill for specialized knowledge.
# Skills: {SKILLS.descriptions()}"""

SYSTEM_PROMPT = """You are a coding agent at {WORKSPACE}.
Use the todo tool to plan multi-step tasks. Mark in_progress before starting, completed when done.
Prefer tools over prose. Use the task tool to delegate exploration or subtasks."""



class DeepCodeAgent:

    def __init__(
        self, 
        config: Settings, 
        middlewares: list = None  # debug 使用
    ):
        self.config = config
        self.agent = self._create_agent(middlewares)

    def _create_agent(self, middlewares: list):
        llm = create_model(self.config.model)
        if not middlewares:
            middlewares = [
                HumanInTheLoopMiddleware(self.init_tool_config()),
                OptSystemMiddleware(workdir=self.config.workspace),
                # TodoListMiddleware(),
                AskUserQuestionMiddleware(),
                # SkillsMiddelware(skills_dir=self.config.skills_dir),
            ]

        checkpointer = MemorySaver()
        agent = create_agent(
            model=llm,
            system_prompt=SYSTEM_PROMPT.format(WORKSPACE=self.config.workspace),
            middleware=middlewares,
            checkpointer=checkpointer
        )
        return agent



    async def ainvoke(
        self,
        message: str,
        thread_id: str | None = None,
        on_progress: Callable | None = None,
        resume: dict | None = None,  # 是否HITL恢复
    ) -> str:
        # 1. 处理输入数据
        config = {"recursion_limit": self.config.recursion_limit}
        if thread_id:
            config["configurable"] = {"thread_id": thread_id}
        input_state = {"messages": [message]}
        if resume:
            input_state = Command(resume=resume)

        # 2. 调用agent
        if on_progress:
            final_output = None
            async for event in self.agent.astream_events(input_state,config=config,version="v2"):
                event_type = event.get("event", "")  # 事件类型
                event_name = event.get("name", "")   # 事件名称


                # 1. HITL 中断处理
                if event_type == "on_chain_stream":
                    chunk = event["data"].get("chunk")
                    if isinstance(chunk, dict) and "__interrupt__" in chunk:
                        interrupt_obj: Interrupt = chunk['__interrupt__'][0]
                        interrupt_value = interrupt_obj.value
                        if isinstance(interrupt_value, dict) and "questions" in interrupt_value: # 检查是否是 AskUserQuestion 请求
                            # AskUserQuestion 请求
                            await on_progress(interrupt_value, type="ask_user_question")
                            return "__ASK_USER_QUESTION__"
                        else:
                            # HITL 请求
                            hitl_request: HITLRequest = interrupt_value
                            await on_progress(hitl_request, type="hitl")
                            return "__HITL_INTERRUPT__"
                    
                # 2. 模型输出 处理
                if event_type == "on_chat_model_end":
                    output = event["data"].get("output")

                    if hasattr(output, "tool_calls") and output.tool_calls:  # 工具调用
                        # 工具调用的模型reasoning输出
                        text_content = self._extract_text_from_message(output)
                        if text_content and text_content.strip():
                            await on_progress(text_content, type="on_progress")
                        final_output = None  # 有工具调用，不是最终输出
                    else:
                        # 最终输出不打印
                        # 非工具调用前输出,保留一轮, 如果还在则证明不是最终输出, 打印
                        if final_output:
                            await on_progress(self._extract_text_from_message(final_output), type="on_progress")
                        text_content = self._extract_text_from_message(output)
                        if text_content and text_content.strip():
                            final_output = output

                # 工具调用事件处理
                elif event_type == "on_tool_start" and event_name:
                    tool_desc = {
                        "type": "tool_hint_start",
                        "tool_name": event_name,
                        "tool_args": event['data'].get('input'),
                        "run_id": event['run_id']
                    }
                    await on_progress(tool_desc, type="tool")
                elif event_type == "on_tool_end" and event_name:
                    tool_content = self._extract_text_from_message(event['data'].get('output'))
                    if tool_content and tool_content.strip():
                        tool_output = {
                            "type": "tool_hint_end",
                            "run_id": event['run_id'],
                            "output": tool_content
                        }
                        await on_progress(tool_output, type="tool")
                elif event_type == "on_tool_error" and event_name:
                    tool_error = {
                        "type": "tool_hint_error",
                        "run_id": event['run_id'],
                        "tool_name": event_name,
                    }
                    await on_progress(tool_error, type="tool")

            # 返回最终输出（优先使用 final_output，否则使用最后一次模型输出）
            output_to_return = final_output
            result = self._extract_response_content({"messages": [output_to_return]})
            return result

        # 无进度回调时直接调用
        state = await self.agent.ainvoke(input_state, config=config)
        return self._extract_response_content(state)

    def _extract_text_from_message(self, message) -> str:
        if hasattr(message, "text"):
            return message.text
        return str(message)

    def _extract_response_content(self, state: dict) -> str:
        messages = state.get("messages", [])
        if not messages:
            return ""

        last_message = messages[-1]
        if hasattr(last_message, "text"):
            return last_message.text
        return str(last_message)


    def init_tool_config(self):
        return {
            "Read": True,
            "Write": True,
            "Bash": True,
            "Edit": True
        }