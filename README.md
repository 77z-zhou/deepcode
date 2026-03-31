# DeepCode 🐽 - AI Coding Agent Based on LangChain

[English](README.md) | [中文](README_CN.md)

An intelligent AI-powered coding agent CLI (based on LangChain) that helps you write, analyze, and understand code with natural language commands.

![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

## Features

- **AI-Powered Code Assistant**: Interact with your codebase using natural language
- **Human-in-the-Loop Approval**: Review and approve tool executions before they run
- **Tabbed Question Interface**: Beautiful TUI for multi-step user interactions with:
  - Tabbed navigation between questions
  - Progress indicator ("Step X of Y")
  - Arrow key navigation (←→ for tabs, ↑↓ for options)
  - Preview panel for options with rich markdown/code preview
  - Dark mode styling with blue highlights
  - Submit validation (all questions must be answered)
  - Inline custom input for "Other" options (supports English/Chinese)
- **Rich Terminal UI**: Beautiful output with markdown rendering and syntax highlighting
- **Multi-Model Support**: Works with OpenAI-compatible APIs (OpenAI, DeepSeek, etc.)
- **Extensible Middleware System**: Add custom behaviors via middleware
- **Async Architecture**: Built on asyncio for responsive interactions

## Installation

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) (recommended package manager)

### Install with uv

```bash
# Clone the repository
git clone <your-repo-url>
cd deepcode

# Install dependencies
uv sync

# Or install in development mode
uv pip install -e .
```

### Install with pip

```bash
pip install -e .
```

## Quick Start

```bash
# Run deepcode
deepcode

# Or with Python
python -m deepcode
```

First run will prompt you to configure:
- API provider (OpenAI, DeepSeek, etc.)
- API key
- Model name
- Workspace directory

## Usage

### Interactive Mode

Start the CLI and chat with the agent:

```bash
deepcode
```

Example interactions:

```
You: Read the main.py file and summarize what it does

You: Add error handling to the parse_config function

You: Create a test for the User class

You: What files use the Database connection?
```

### Built-in Commands

- `/help` - Show help information
- `/clear` - Clear the screen
- `/model` - Change the AI model
- `/compact` - Compact conversation context
- `/cost` - Show API usage costs
- `/exit` - Exit the program
- `/init` - Reinitialize configuration

## Configuration

Configuration is stored in your project directory. The first run will guide you through setup:

```python
# Sample configuration structure
{
    "model": "gpt-4",           # Model identifier
    "api_key": "sk-...",        # API key
    "base_url": null,           # Custom API base URL (optional)
    "workspace": ".",           # Working directory
    "recursion_limit": 50,      # Agent recursion limit
    "skills_dir": ".claude/skills"  # Custom skills directory
}
```

## Project Structure

```
deepcode/
├── deepcode/
│   ├── __init__.py
│   ├── __main__.py           # Entry point
│   ├── cli/                  # CLI interface
│   │   ├── app.py            # Main CLI application
│   │   ├── commands/         # Built-in commands
│   │   └── utils.py          # TUI components (tabbed interface)
│   ├── core/
│   │   ├── agent.py          # Main agent logic
│   │   ├── model.py          # Model factory
│   │   └── middleware/       # Agent middleware
│   ├── config/               # Configuration management
│   └── bus/                  # Message bus for async communication
├── tests/                    # Test suite
├── pyproject.toml           # Project metadata
└── README.md
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=deepcode
```

### Code Style

This project follows standard Python conventions with type hints.

### Key Components

- **Tabbed Question Interface** (`deepcode/cli/utils.py`):
  - `_present_user_questions()` - Main TUI entry point
  - Full prompt_toolkit implementation with custom key bindings
  - Rich markdown preview with syntax highlighting

- **Agent** (`deepcode/core/agent.py`):
  - LangGraph-based agent with LangChain integration
  - Streaming responses with progress callbacks
  - HITL (Human-in-the-Loop) support

- **Message Bus** (`deepcode/bus/`):
  - Async pub/sub for inbound/outbound messages
  - Coordinates between CLI and agent

## Dependencies

- **langchain** - Agent framework
- **langgraph** - Agent orchestration
- **prompt_toolkit** - Terminal UI framework
- **rich** - Rich text and formatting
- **typer** - CLI framework
- **pydantic** - Data validation
- **loguru** - Logging
- **questionary** - Interactive prompts

## License

MIT License - see LICENSE file for details

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## Acknowledgments

Built with:
- [LangChain](https://github.com/langchain-ai/langchain) - AI agent framework
- [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) - Terminal UI
- [Rich](https://github.com/Textualize/rich) - Terminal formatting
