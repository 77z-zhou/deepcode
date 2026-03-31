from typing import Dict, List, Optional, Type, Any
from deepcode.cli.commands.base import Command


class CommandRegistry:
    def __init__(self):
        self._commands: Dict[str, Command] = {}

    def register(self, command: Command) -> None:
        self._commands[command.name] = command
        # Register aliases
        for alias in command.aliases:
            self._commands[alias] = command

    def get(self, name: str) -> Optional[Command]:
        # Strip leading slash if present
        key = name.lstrip("/")
        return self._commands.get(key)

    def is_command(self, input_text: str) -> bool:
        return input_text.startswith("/")

    def list_commands(self) -> List[Command]:
        seen = set()
        unique_commands = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                unique_commands.append(cmd)
        return unique_commands

    def execute(self, input_text: str, context: Dict[str, Any]) -> str:
        # Split into command name and args
        parts = input_text.strip().split(None, 1)
        cmd_name = parts[0].lstrip("/")
        args = parts[1].split() if len(parts) > 1 else []

        command = self._commands.get(cmd_name)
        if not command:
            available = ", ".join(f"/{name}" for name in set(c.name for c in self._commands.values()))
            raise ValueError(f"Unknown command: /{cmd_name}. Available: {available}")

        return command.execute(args, context)
