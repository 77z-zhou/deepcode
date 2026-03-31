"""Built-in slash commands."""

from typing import List, Dict, Any, Union
from rich.console import Console
from rich.table import Table

from deepcode.cli.commands.base import Command

console = Console()


def _get_message_content(msg: Union[Dict[str, Any], Any]) -> str:
    if isinstance(msg, dict):
        return msg.get("content", "")
    # LangChain message object
    return str(getattr(msg, "content", ""))


class HelpCommand(Command):
    """Display help information."""

    name = "help"
    description = "Show available commands and help"
    aliases = ["?", "h"]

    def execute(self, args: List[str], context: Dict[str, Any]) -> str:
        """Execute help command."""
        registry = context.get("command_registry")

        if not registry:
            return "No commands available"

        if args:
            # Help for specific command
            cmd = registry.get(args[0])
            if cmd:
                return cmd.get_help()
            return f"Unknown command: /{args[0]}"

        # List all commands
        commands = registry.list_commands()

        table = Table(title="Available Commands")
        table.add_column("Command", style="cyan")
        table.add_column("Description", style="white")

        for cmd in commands:
            aliases = ""
            if cmd.aliases:
                aliases = f" (aliases: {', '.join('/' + a for a in cmd.aliases)})"
            table.add_row(f"/{cmd.name}{aliases}", cmd.description)

        console.print(table)
        return ""


class ClearCommand(Command):
    """Clear conversation history."""

    name = "clear"
    description = "Clear conversation history"
    aliases = ["reset", "cls"]

    def execute(self, args: List[str], context: Dict[str, Any]) -> str:
        """Execute clear command."""
        agent = context.get("agent")
        if agent and hasattr(agent, "clear_history"):
            agent.clear_history()
            return "Conversation history cleared."
        return "Cannot clear history: agent does not support this operation."


class ModelCommand(Command):
    """Switch or display current model."""

    name = "model"
    description = "Switch to a different model or show current model"
    aliases = ["llm"]

    def execute(self, args: List[str], context: Dict[str, Any]) -> str:
        """Execute model command."""
        config = context.get("config", {})

        if not args:
            current = config.get("model_name", "unknown")
            return f"Current model: {current}"

        new_model = args[0]
        # Update model in context
        config["model_name"] = new_model
        return f"Model switched to: {new_model}\nNote: This will take effect on next agent invocation."


class CompactCommand(Command):
    """Compact conversation context."""

    name = "compact"
    description = "Compact conversation history to save tokens"
    aliases = ["compress"]

    def execute(self, args: List[str], context: Dict[str, Any]) -> str:
        """Execute compact command."""
        state = context.get("state", {})
        messages = state.get("messages", [])

        if not messages:
            return "No messages to compact."

        # Keep last N messages
        keep = 10
        if args and args[0].isdigit():
            keep = int(args[0])

        original_count = len(messages)
        state["messages"] = messages[-keep:]

        return f"Compacted: {original_count} messages -> {keep} messages"


class CostCommand(Command):
    """Show token usage and cost estimate."""

    name = "cost"
    description = "Show token usage and cost estimate"
    aliases = ["tokens", "usage"]

    def execute(self, args: List[str], context: Dict[str, Any]) -> str:
        """Execute cost command."""
        state = context.get("state", {})
        messages = state.get("messages", [])

        if not messages:
            return "No messages to calculate cost."

        # Simple token estimation (rough: 1 token ≈ 4 characters)
        total_chars = sum(len(_get_message_content(msg)) for msg in messages)
        estimated_tokens = total_chars // 4

        # GLM-4 pricing (rough estimate)
        input_tokens = estimated_tokens // 2
        output_tokens = estimated_tokens // 2

        # Pricing (example - adjust based on actual GLM pricing)
        input_cost = input_tokens * 0.00001  # $0.01 per 1M tokens
        output_cost = output_tokens * 0.00002  # $0.02 per 1M tokens
        total_cost = input_cost + output_cost

        return f"""Token Usage Estimate:
  Input tokens: ~{input_tokens:,}
  Output tokens: ~{output_tokens:,}
  Total tokens: ~{estimated_tokens:,}

Cost Estimate: ${total_cost:.4f}

Note: This is a rough estimate. Actual usage may vary."""


class ExitCommand(Command):
    """Exit the agent."""

    name = "exit"
    description = "Exit DeepCode"
    aliases = ["quit", "q"]

    def execute(self, args: List[str], context: Dict[str, Any]) -> str:
        """Execute exit command."""
        # Signal to exit the main loop
        context["should_exit"] = True
        return "Goodbye!"


class InitCommand(Command):
    """Initialize project configuration."""

    name = "init"
    description = "Initialize DeepCode in current directory"
    aliases = ["initialize"]

    def execute(self, args: List[str], context: Dict[str, Any]) -> str:
        """Execute init command."""
        import os
        from pathlib import Path

        cwd = Path(os.getcwd())
        deepcode_dir = cwd / ".deepcode"

        if deepcode_dir.exists():
            return "DeepCode already initialized in this directory."

        # Create directory structure
        deepcode_dir.mkdir()
        (deepcode_dir / "skills").mkdir()
        (deepcode_dir / "memory").mkdir()

        # Create AGENTS.md
        agents_md = deepcode_dir / "AGENTS.md"
        agents_md.write_text("""---
name: deepcode-agent
description: DeepCode coding agent
---

# DeepCode Agent

You are a coding agent that helps with software engineering tasks.
""")

        # Create settings.json
        settings = deepcode_dir / "settings.json"
        settings.write_text("""{
  "model": {
    "provider": "openai",
    "base_url": "https://open.bigmodel.cn/api/paas/v4/",
    "model_name": "glm-4",
    "api_key_env": "GLM_API_KEY"
  },
  "permissions": {
    "bash": "auto",
    "edit": "auto",
    "network": "ask"
  },
  "theme": "dark"
}
""")

        # Create mcp_servers.json
        mcp = deepcode_dir / "mcp_servers.json"
        mcp.write_text("""{
  "mcpServers": {}
}
""")

        return f"""DeepCode initialized successfully!

Created:
  {deepcode_dir}/AGENTS.md
  {deepcode_dir}/settings.json
  {deepcode_dir}/mcp_servers.json
  {deepcode_dir}/skills/
  {deepcode_dir}/memory/

Edit these files to configure your agent."""
