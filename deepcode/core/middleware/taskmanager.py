from pathlib import Path
import json

from langchain_core.tools import BaseTool,tool
from langchain.agents.middleware import AgentMiddleware



class TaskManager:
    def __init__(self, tasks_dir: Path):
        self.dir = tasks_dir
        self.dir.mkdir(exist_ok=True)
        self._next_id = self._max_id() + 1

    def _max_id(self) -> int:
        ids = [int(f.stem.split("_")[1]) for f in self.dir.glob("task_*.json")]
        return max(ids) if ids else 0

    def _load(self, task_id: int) -> dict:
        path = self.dir / f"task_{task_id}.json"
        if not path.exists():
            raise ValueError(f"Task {task_id} not found")
        return json.loads(path.read_text())

    def _save(self, task: dict):
        path = self.dir / f"task_{task['id']}.json"
        path.write_text(json.dumps(task, indent=2))

    def _create_task_create_tool(self):
        @tool(description="Create a new task.")
        def task_create(subject: str, description: str = ""):
            task = {
                "id": self._next_id, "subject": subject, "description": description,
                "status": "pending", "blockedBy": [], "blocks": [], "owner": "",
            }
            self._save(task)
            self._next_id += 1
            return json.dumps(task, indent=2)
        return task_create
    
    def _create_task_update_tool(self):
        @tool(description="Update a task's status or dependencies.")
        def task_update(task_id: int, status: str = None,
                add_blocked_by: list = None, add_blocks: list = None) -> str:
            task = self._load(task_id)
            if status:
                if status not in ("pending", "in_progress", "completed"):
                    raise ValueError(f"Invalid status: {status}")
                task["status"] = status
                # When a task is completed, remove it from all other tasks' blockedBy
                if status == "completed":
                    self._clear_dependency(task_id)
            if add_blocked_by:
                task["blockedBy"] = list(set(task["blockedBy"] + add_blocked_by))
            if add_blocks:
                task["blocks"] = list(set(task["blocks"] + add_blocks))
                # Bidirectional: also update the blocked tasks' blockedBy lists
                for blocked_id in add_blocks:
                    try:
                        blocked = self._load(blocked_id)
                        if task_id not in blocked["blockedBy"]:
                            blocked["blockedBy"].append(task_id)
                            self._save(blocked)
                    except ValueError:
                        pass
            self._save(task)
            return json.dumps(task, indent=2)
        return task_update


    def _create_task_get_tool(self):
        @tool(description="Get full details of a task by ID.")
        def task_get(task_id: int) -> str:
            return json.dumps(self._load(task_id), indent=2)
        return task_get
    
    def _create_task_list_tool(self):
        @tool(description="List all tasks with status summary.")
        def task_list(self) -> str:
            tasks = []
            for f in sorted(self.dir.glob("task_*.json")):
                tasks.append(json.loads(f.read_text()))
            if not tasks:
                return "No tasks."
            lines = []
            for t in tasks:
                marker = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}.get(t["status"], "[?]")
                blocked = f" (blocked by: {t['blockedBy']})" if t.get("blockedBy") else ""
                lines.append(f"{marker} #{t['id']}: {t['subject']}{blocked}")
            return "\n".join(lines)
        return task_list



    def _clear_dependency(self, completed_id: int):
        """Remove completed_id from all other tasks' blockedBy lists."""
        for f in self.dir.glob("task_*.json"):
            task = json.loads(f.read_text())
            if completed_id in task.get("blockedBy", []):
                task["blockedBy"].remove(completed_id)
                self._save(task)




class TaskManagerMiddleware(AgentMiddleware):

    def __init__(self, tasks_dir: Path):
        self.task_manager = TaskManager(tasks_dir)
        self.tools = [
            self.task_manager._create_task_create_tool(),
            self.task_manager._create_task_update_tool(),
            self.task_manager._create_task_get_tool(),
            self.task_manager._create_task_list_tool(),

        ]


