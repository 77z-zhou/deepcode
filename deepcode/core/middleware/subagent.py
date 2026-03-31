from pathlib import Path
from typing import Annotated

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import BaseTool, StructuredTool
from langchain.messages import HumanMessage
from langchain.agents import create_agent
from langchain.chat_models import BaseChatModel



TASK_TOOL_DESCRIPTION = """Spawn a subagent with fresh context. It shares the filesystem but not conversation history."""


SUBAGENT_SYSTEM = "You are a coding subagent at {workdir}. Complete the given task, then summarize your findings."

class SubAgentMiddleware(AgentMiddleware):

    def __init__(
        self, 
        workdir: Path, 
        model: BaseChatModel,
        sub_agent_middleware: list[AgentMiddleware] = [],
        sub_agent_tools: list[BaseTool] = []
    ):
        self.workdir = workdir
        self.model = model
        self.sub_agent_middleware = sub_agent_middleware
        self.sub_agent_tools = sub_agent_tools

        self.tools = [self._create_run_subagent()]
    
    def _create_run_subagent(self) -> BaseTool:
        def run_subagent(prompt: Annotated[str, "Short description of the task"]) -> str:
            sub_message = HumanMessage(content=prompt)
            sub_agent = create_agent(
                model=self.model,
                tools=self.sub_agent_tools,
                middleware=self.sub_agent_middleware,
                system_prompt=SUBAGENT_SYSTEM.format(workdir=self.workdir),
            )
            response = sub_agent.invoke({"messages": [sub_message]})
            ai_msg = response['messages'][-1].content
            if ai_msg:
                return ai_msg
            return "subagent failed"
        
        async def arun_subagent(prompt:Annotated[str, "Short description of the task"]) -> str:
            sub_message = HumanMessage(content=prompt)
            sub_agent = create_agent(
                model=self.model,
                tools=self.sub_agent_tools,
                middleware=self.sub_agent_middleware,
                system_prompt=SUBAGENT_SYSTEM.format(workdir=self.workdir),
            )
            response = await sub_agent.ainvoke({"messages": [sub_message]})
            ai_msg = response['messages'][-1].content
            if ai_msg:
                return ai_msg
            return "subagent failed"
        
        
        return StructuredTool.from_function(
            name="task",
            description=TASK_TOOL_DESCRIPTION,
            func=run_subagent,
            coroutine=arun_subagent
        )


            

