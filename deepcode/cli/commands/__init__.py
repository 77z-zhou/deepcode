from deepcode.cli.commands.base import Command
from deepcode.cli.commands.registry import CommandRegistry

__all__ = [
    "Command",
    "CommandRegistry",
]

registry = CommandRegistry()