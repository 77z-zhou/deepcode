import threading
import uuid
import subprocess
from pathlib import Path

from langchain.tools import tool
from langchain.agents.middleware import AgentMiddleware
from langchain.agents import AgentState
from langchain.messages import AIMessage, HumanMessage


class BackgroundManager:
    def __init__(self, work_dir: Path):
        self.work_dir = work_dir
        self.tasks = {}  # task_id -> {status, result, command}
        self._notification_queue = []  # completed task results
        self._lock = threading.Lock()


    def _create_background_run_tool(self):
        @tool(description="Run command in background thread. Returns task_id immediately.")
        def background_run(command: str) -> str:
            task_id = str(uuid.uuid4())[:8]
            self.tasks[task_id] = {"status": "running", "result": None, "command": command}
            thread = threading.Thread(
                target=self._execute, args=(task_id, command), daemon=True
            )
            thread.start()
            return f"Background task {task_id} started: {command[:80]}"
        return background_run
    def _execute(self, task_id: str, command: str):
        try:
            r = subprocess.run(
                command, shell=True, cwd=self.work_dir,
                capture_output=True, text=True, timeout=300
            )
            output = (r.stdout + r.stderr).strip()[:50000]
            status = "completed"
        except subprocess.TimeoutExpired:
            output = "Error: Timeout (300s)"
            status = "timeout"
        except Exception as e:
            output = f"Error: {e}"
            status = "error"
        self.tasks[task_id]["status"] = status
        self.tasks[task_id]["result"] = output or "(no output)"
        with self._lock:
            self._notification_queue.append({
                "task_id": task_id,
                "status": status,
                "command": command[:80],
                "result": (output or "(no output)")[:500],
            })

    def _create_check_background_tool(self):
        @tool(description="Check background task status. Omit task_id to list all.")
        def check_background(self, task_id: str = None) -> str:
            if task_id:
                t = self.tasks.get(task_id)
                if not t:
                    return f"Error: Unknown task {task_id}"
                return f"[{t['status']}] {t['command'][:60]}\n{t.get('result') or '(running)'}"
            lines = []
            for tid, t in self.tasks.items():
                lines.append(f"{tid}: [{t['status']}] {t['command'][:60]}")
            return "\n".join(lines) if lines else "No background tasks."
        return check_background
    
    def drain_notifications(self) -> list:
        with self._lock:
            notifs = list(self._notification_queue)
            self._notification_queue.clear()
        return notifs
    


class BackgroundTaskMiddleware(AgentMiddleware):
    def __init__(self, work_dir: Path):
        self.background_manager = BackgroundManager(work_dir)

        self.tools = [
            self.background_manager._create_background_run_tool(),
            self.background_manager._create_check_background_tool(),
        ]

    def before_model(self, state: AgentState, runtime):
        notif_messages = []
        notifs = self.background_manager.drain_notifications()
        if notifs:
            notif_text = "\n".join(
                f"[bg:{n['task_id']}] {n['status']}: {n['result']}" for n in notifs
            )
            notif_messages.append(HumanMessage(content=notif_text))
            notif_messages.append(AIMessage(content="Noted background results."))
        if not notif_messages:
             return None

        return {"messages": notif_messages}
    
    async def abefore_model(self, state, runtime):
        return await self.before_model(state, runtime)

