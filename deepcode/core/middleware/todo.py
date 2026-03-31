from typing import Literal, Annotated, NotRequired, Any
from typing_extensions import TypedDict


from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState, OmitFromInput
from langchain_core.tools import tool, InjectedToolCallId
from langchain_core.messages import ToolMessage, AIMessage
from langgraph.types import Command
from langgraph.runtime import Runtime

class Todo(TypedDict):
    content: str
    status: Literal["pending", "in_progress", "completed"]

class TodoListState(AgentState):
    todos: Annotated[NotRequired[list[Todo]], OmitFromInput]

TODO_TOOL_DESCRIPTION = """Update task list. Track progress on multi-step tasks."""


class TodoListMiddleware(AgentMiddleware):

    state_schema = TodoListState

    def __init__(self):

        self.rounds_since_todo = 0

        @tool(description=TODO_TOOL_DESCRIPTION)
        def todo(
            todos: list[Todo], tool_call_id: Annotated[str, InjectedToolCallId]
        ) -> Command[Any]:
            if len(todos) > 20:
                return "Error: Max 20 todos allowed."

            in_progress_count  = 0
            for todo in todos:
                if todo['status'] == 'in_progress':
                    in_progress_count += 1
            if in_progress_count > 1:
                return "Error: Only one task can be in progress at a time."

            return Command(
                update={
                    "todos": todos,
                    "messages": [
                        ToolMessage(f"Updated todo list to {todos}", tool_call_id=tool_call_id)
                    ],
                }
            )
        self.tools = [todo]


    def before_model(self, state: TodoListState, runtime: Runtime):
        messages = state["messages"]
        if not messages:
            return None
        
        last_ai_msg = next((msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None)
        if not last_ai_msg or not last_ai_msg.tool_calls:
            return None
        
        # count rounds since todo
        is_call_todo = False
        for tool_call in last_ai_msg.tool_calls:
            tool_name = tool_call['name']
            if tool_name == 'todo':
                is_call_todo = True
                self.rounds_since_todo = 0
        if is_call_todo == False:
            self.rounds_since_todo += 1
        
        if self.rounds_since_todo < 3: 
            return None
        
        # if 3 rounds not calling todo, inject nag reminder
        last_tool_msg = next((msg for msg in reversed(messages) if isinstance(msg, ToolMessage)), None)
        
        blocks = last_tool_msg.content_blocks
        blocks.insert(0, {"type": "text", "text": "<reminder>Update your todos.</reminder>"})
        return {"messages": messages}

    async def abefore_model(self, state: TodoListState, runtime: Runtime):
        return self.before_model(state, runtime)
            
           
        

        


