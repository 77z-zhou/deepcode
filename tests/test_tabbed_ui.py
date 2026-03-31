"""
Test script for the new tabbed CLI question interface.
Run this to verify the tabbed UI works correctly.
"""
import asyncio
from rich.console import Console

# Import the function to test
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from deepcode.cli.utils import _present_user_questions


async def test_tabbed_ui():
    """Test the tabbed UI with sample questions."""
    console = Console()

    # Sample questions matching the AskUserQuestion format
    questions = [
        {
            "question": "What best describes your role?",
            "header": "Role",
            "options": [
                {
                    "label": "Software Developer",
                    "description": "I write code as my primary job",
                },
                {
                    "label": "Product Manager",
                    "description": "I focus on product strategy and features",
                },
                {
                    "label": "Designer",
                    "description": "I create user interfaces and experiences",
                },
            ],
        },
        {
            "question": "What is your primary focus area?",
            "header": "Focus Area",
            "options": [
                {
                    "label": "Backend Development",
                    "description": "Server-side logic, databases, APIs",
                },
                {
                    "label": "Frontend Development",
                    "description": "User interfaces, client-side logic",
                },
            ],
        },
        {
            "question": "Choose a framework to see preview",
            "header": "Framework",
            "options": [
                {
                    "label": "React",
                    "description": "Facebook's JavaScript library",
                    "preview": "```jsx\nfunction App() {\n  return <div>Hello World</div>;\n}\n```",
                },
                {
                    "label": "Vue",
                    "description": "Progressive JavaScript framework",
                    "preview": "```vue\n<template>\n  <div>Hello World</div>\n</template>\n```",
                },
            ],
        },
        {
            "question": "What help style do you prefer?",
            "header": "Help Style",
            "multiSelect": True,
            "options": [
                {
                    "label": "Code Examples",
                    "description": "Show me code snippets",
                },
                {
                    "label": "Explanations",
                    "description": "Detailed text explanations",
                },
            ],
        },
    ]

    console.print("[bold cyan]Testing Tabbed Question Interface[/bold cyan]")
    console.print("[dim]Use arrow keys to navigate. Press Enter to confirm, Esc to cancel.[/dim]\n")

    answers = await _present_user_questions(questions, console)

    console.print("\n[bold green]Answers received:[/bold green]")
    for question, answer in answers.items():
        console.print(f"  {question}: [cyan]{answer}[/cyan]")


if __name__ == "__main__":
    asyncio.run(test_tabbed_ui())
