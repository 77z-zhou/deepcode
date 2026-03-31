import typer
from rich.console import Console
from rich.prompt import Prompt
from prompt_toolkit import PromptSession

import asyncio
from pathlib import Path
from contextlib import nullcontext
from typing import Literal

from deepcode import __logo__, __version__
from deepcode.core.agent import DeepCodeAgent
from deepcode.config.settings import Settings
from deepcode.bus import InboundMessage, OutboundMessage, MessageBus
from deepcode.config.loader import get_current_config
from deepcode.cli.commands import registry
from deepcode.cli.commands.builtin import (
    HelpCommand, ClearCommand, ModelCommand, CompactCommand,
    CostCommand, ExitCommand, InitCommand
)
from deepcode.cli.utils import (
    _ThinkingSpinner,
    banner_print,
    _init,
    _init_prompt_session,
    _restore_terminal,
    _flush_pending_tty_input,
    _read_user_input,
    _print_agent_response,
    _hitl_approve_simple,
    _print_interactive_progress,
    _present_user_questions,
)



# 创建CLI
app = typer.Typer(
    name="deepcode"
)
console = Console()


# 注册内置命令
def register_builtin_commands():
    """Register all built-in slash commands."""
    # registry.register(HelpCommand())
    # registry.register(ClearCommand())
    # registry.register(ModelCommand())
    # registry.register(CompactCommand())
    # registry.register(CostCommand())
    # registry.register(ExitCommand())
    registry.register(InitCommand())


# 创建运行命令
@app.command()
def main():
    # 0. 配置加载
    config = get_current_config()

    # 1. 欢迎界面
    banner_print(console, config)

    # 2. 初始化prompt session
    _init_prompt_session(config)

    # 3. 创建智能体 以及上下文
    agent, bus, context = _init(config)
    
    # 4. 交互循环
    async def run_interactive():
        turn_done = asyncio.Event()
        turn_done.set()
        turn_response: list[str] = []
        _thinking: _ThinkingSpinner | None = _ThinkingSpinner(enabled=True, console=console)

        agent_task = asyncio.create_task(_run_agent_dispatcher(agent, bus, config))
        outbound_task = asyncio.create_task(_consume_outbound(_thinking, bus, config, turn_done, turn_response))

        try:
            while True:             
                try:
                    # 1.读取用户输入
                    _flush_pending_tty_input()
                    user_input = await _read_user_input()
                    command = user_input.strip()
                    if not command:
                        continue

                    # 2.处理slash command
                    if registry.is_command(command):
                        result = registry.execute(command, context)
                        _print_agent_response(result, True)
                    
                        if context.get("should_exit"):
                            _restore_terminal()
                            console.print("\nGoodbye!")
                            break
                        continue
                    
                    # 3. 处理message
                    turn_done.clear()
                    turn_response.clear()
                    # 发送消息
                    await bus.publish_inbound(
                        InboundMessage(
                            channel="cli",
                            sender_id="user",
                            chat_id="direct",
                            content=user_input,
                        )
                    )

                    # 4. 监听响应
                    # _thinking = 
                    with _thinking:
                        await turn_done.wait()
                    # _thinking = None

                    if turn_response:
                        _print_agent_response(turn_response[0], render_markdown=True)
                except (KeyboardInterrupt, EOFError):
                    _restore_terminal()
                    console.print("\nGoodbye!")
                    break
        finally:
            # 退出时取消任务
            agent_task.cancel()
            outbound_task.cancel()
            await asyncio.gather(agent_task, outbound_task, return_exceptions=True)

    asyncio.run(run_interactive())



async def _run_agent_dispatcher(agent: DeepCodeAgent, bus: MessageBus, config: Settings):
    """生产者: 将 inbound msg 分发给 agent处理,并发布进度消息到bus"""
    while True:
        try:
            msg = await bus.consume_inbound()  # 阻塞等待inbound msg

            # 1. 构建 session_key 作为 thread_id
            thread_id = f"{msg.channel}:{msg.chat_id}"

            # 2. 保存原消息的 metadata (用于回复原消息)
            original_metadata = msg.metadata.copy()

            # 3. 处理 HITL 响应
            resume_data = None
            if msg.metadata.get("_hitl_response"):
                resume_data = msg.metadata.get("_hitl_data")

            # 4. 处理 AskUserQuestion 响应
            if msg.metadata.get("_ask_user_question_response"):
                resume_data = {
                    "user_answers": msg.metadata.get("_question_answers"),
                }

            # 进度回调函数：将进度发布到 bus
            async def on_progress(content: str | dict, type: Literal["hitl", "ask_user_question", "tool", "on_progress"]) -> None:
                """将工具和文本进度转换为 bus 消息"""

                # 处理HITL
                if type == "hitl":
                    await bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="",
                            metadata={
                                "type": type,
                                "_hitl_data": content,
                            },
                        )
                    )
                # 处理AskUserQuestion
                elif type == "ask_user_question":
                    await bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content="",
                            metadata={
                                "type": type,
                                "_question_data": content,
                            },
                        )
                    )
                else:
                    #  progress / tool
                    await bus.publish_outbound(
                        OutboundMessage(
                            channel=msg.channel,
                            chat_id=msg.chat_id,
                            content=content,
                            metadata={"type": type},
                        )
                    )

            # agent 处理消息
            response = await agent.ainvoke(
                msg.content,
                thread_id=thread_id,
                resume=resume_data,
                on_progress=on_progress
            )
            if response == "__HITL_INTERRUPT__":
                continue
            if response == "__ASK_USER_QUESTION__":
                continue

            # 发送最终响应到 bus (带上原消息 metadata 以支持回复功能)
            await bus.publish_outbound(
                OutboundMessage(
                    channel=msg.channel,
                    chat_id=msg.chat_id,
                    content=response,
                    metadata=original_metadata,  # 传递原消息 metadata (如 message_id)
                )
            )

        except asyncio.CancelledError:
            break
        except Exception as e:
            raise e


async def _consume_outbound(_thinking, bus: MessageBus, config: Settings, turn_done, turn_response):
    """消费者: 消费来自bus的 outbound msg."""
    while True:
        try:
            # 1. 监听consume_outbound消息
            msg = await asyncio.wait_for(bus.consume_outbound(), timeout=1.0)
            type = msg.metadata.get("type")
            
            # 2. 处理 HITL 请求
            if type == "hitl":
                hitl_data = msg.metadata.get("_hitl_data", {})
                action_requests = hitl_data.get("action_requests", [])

                # 逐个确认每个工具
                decisions = []
                # 暂停 thinking spinner
                with _thinking.pause() if _thinking else nullcontext():
                    for i, ar in enumerate(action_requests):
                        action, reason = await _hitl_approve_simple(
                            tool_name=ar.get("name", "unknown"),
                            tool_args=ar.get("args", ""),
                            console=console
                        )

                        # 构建 Decision 对象
                        if action in ("approve", "always_approve"):
                            from langchain.agents.middleware.human_in_the_loop import ApproveDecision
                            decisions.append(ApproveDecision(type="approve"))
                        else:  # reject
                            from langchain.agents.middleware.human_in_the_loop import RejectDecision
                            decisions.append(RejectDecision(type="reject", message=reason))

                # 构建 HITLResponse
                from langchain.agents.middleware.human_in_the_loop import HITLResponse
                hitl_response = HITLResponse(decisions=decisions)

                # 通过 bus 发送 HITL 响应
                await bus.publish_inbound(
                    InboundMessage(
                        channel=msg.channel,
                        sender_id="user",
                        chat_id=msg.chat_id,
                        content="",
                        metadata={
                            "_hitl_response": True,
                            "_hitl_data": hitl_response,
                        },
                    )
                )
                continue

            # 2.5. 处理 AskUserQuestion 请求
            if type == "ask_user_question":
                question_data = msg.metadata.get("_question_data", {})
                questions = question_data.get("questions", [])

                # 暂停 thinking spinner 并展示问题
                answers = []
                with _thinking.pause() if _thinking else nullcontext():
                    for question in questions:
                        answer = await _present_user_questions(question, console)
                        answers.append(answer)
                
                # 通过 bus 发送答案
                await bus.publish_inbound(
                    InboundMessage(
                        channel=msg.channel,
                        sender_id="user",
                        chat_id=msg.chat_id,
                        content="",
                        metadata={
                            "_ask_user_question_response": True,
                            "_question_answers": answers,
                        },
                    )
                )
                continue
           
            
            # 3. 处理进度消息（受配置控制）
            elif type in ['tool', 'on_progress']:
                await _print_interactive_progress(msg.content, _thinking, console)

            # 4. AI msg最终输出
            elif not turn_done.is_set():
                if msg.content:
                    turn_response.append(msg.content)
                turn_done.set()


        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break






