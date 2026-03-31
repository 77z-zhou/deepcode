import os
import sys
import select
from pathlib import Path
from contextlib import contextmanager, nullcontext
from typing import TypedDict


from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt
import questionary

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit import print_formatted_text
from prompt_toolkit.formatted_text import ANSI, HTML
from prompt_toolkit.styles import Style
from prompt_toolkit.layout import Layout, HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import Application

from deepcode.bus import MessageBus
from deepcode.core.agent import DeepCodeAgent
from deepcode.config.settings import Settings
from deepcode import __logo__, __version__

# 记录用户输入
_PROMPT_SESSION: PromptSession | None = None
_SAVED_TERM_ATTRS = None

class _ThinkingSpinner:
    """Spinner 上下文管理器，支持暂停."""

    def __init__(self, enabled: bool, console: Console):
        self._spinner = console.status(
            "[dim]Thinking...[/dim]", spinner="dots"
        ) if enabled else None
        self._active = False

    def __enter__(self):
        if self._spinner:
            self._spinner.start()
        self._active = True
        return self

    def __exit__(self, *exc):
        self._active = False
        if self._spinner:
            self._spinner.stop()
        return False

    @contextmanager
    def pause(self):
        """打印进度时暂时停止旋转器."""
        if self._spinner and self._active:
            self._spinner.stop()
        try:
            yield
        finally:
            if self._spinner and self._active:
                self._spinner.start()

# ================ prompt session 和 CLI 启动退出管理 ================
def _init_prompt_session(config: Settings) -> None:
    """初始化 prompt_toolkit 会话，保存会话历史到 ~/.deepcode/cli_history.txt."""

    global _PROMPT_SESSION, _SAVED_TERM_ATTRS

    # 保存终端状态以便退出时恢复
    try:
        import termios  
        # 保存当前终端（stdin）的原始输入配置
        _SAVED_TERM_ATTRS = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass

    _PROMPT_SESSION = PromptSession(
        history=FileHistory(str(config.cli_history_file)),
        enable_open_in_editor=False,
        multiline=False,  # 是否默认启用多行输入模式。
    )

def _restore_terminal() -> None:
    """退出时恢复终端原始状态(echo、缓冲)"""
    if _SAVED_TERM_ATTRS is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _SAVED_TERM_ATTRS)
    except Exception:
        pass


# ============= banner 打印 ===============
def banner_print(console: Console, config):
    """ 打印banner"""
    console.print(
        Panel.fit(
            f"[bold blue]DeepCode[/bold blue]\n"
            f"[dim]Loaded Model: {config.model.model_name}[/dim]\n"
            f"[dim]Workspace: {config.workspace}[/dim]",
            border_style="blue"
        )
    )

# ============= Agent, Bus, Context 初始化 ===========
def _init(config: Settings):
    """ 初始化 deepcode agent,  bus, context"""
    agent = DeepCodeAgent(config)
    bus = MessageBus()
    context = {
        "agent": agent,
        "config": config,
        "state": {"messages": []}
    }
    return agent, bus, context



# ============ 用户输入处理 ===========
def _flush_pending_tty_input() -> None:
    """丢弃用户在等待期间输入的字符."""
    try:
        fd = sys.stdin.fileno()
        if not os.isatty(fd):
            return
    except Exception:
        return

    try:
        import termios
        termios.tcflush(fd, termios.TCIFLUSH)
        return
    except Exception:
        pass

    try:
        while True:
            ready, _, _ = select.select([fd], [], [], 0)
            if not ready:
                break
            if not os.read(fd, 4096):
                break
    except Exception:
        return

async def _read_user_input() -> str:
    """异步读取用户输入(支持 Ctrl+D → KeyboardInterrupt)."""
    if _PROMPT_SESSION is None:
        raise RuntimeError("Call _init_prompt_session() first")
    try:
        with patch_stdout():
            return await _PROMPT_SESSION.prompt_async(
                HTML("<b fg='ansiblue'>You:</b> "),
            )
    except EOFError as exc:
        raise KeyboardInterrupt from exc





# =============== 消息打印 =====================
def _make_console() -> Console:
    """创建新的 Rich 控制台实例"""
    return Console(file=sys.stdout)

def _render_interactive_ansi(render_fn, console) -> str:
    """将 Rich 输出转为 ANSI,与 prompt_toolkit 兼容."""
    ansi_console = Console(
        force_terminal=True,
        color_system=console.color_system or "standard",
        width=console.width,
    )
    with ansi_console.capture() as capture:
        render_fn(ansi_console)
    return capture.get()

def _print_agent_response(response: str, render_markdown: bool) -> None:
    """Rich 打印 agent 最终响应(带 logo、Markdown)."""
    c = _make_console()
    c.print()
    c.print(f"[cyan]{__logo__} DeepCode[/cyan]")
    content = Markdown(response) if render_markdown else response
    c.print(content)
    c.print()

async def _print_interactive_line(text: str, console) -> None:
    """在交互模式下打印进度行(异步安全)."""
    def _write() -> None:
        ansi = _render_interactive_ansi(
            lambda c: c.print(f"  [dim]↳ {text}[/dim]"), console
        )
        print_formatted_text(ANSI(ansi), end="")

    from prompt_toolkit.application import run_in_terminal
    await run_in_terminal(_write)



async def _print_progress_info(content, console):
    from prompt_toolkit.application import run_in_terminal
    def _render_func(c: Console) -> None:
        if isinstance(content, str):
            ctt = content.lstrip("\n")
            c.print(f"[white]●[/white] [dim]{ctt}[/dim]")  # AI message 输出
            return
        
        tool_type = content.get("type")
        tool_name = content.get("tool_name", "")

        if tool_type == "tool_hint_start":  # 工具执行开始
            tool_args = content.get("tool_args", {})
            args_str = str(tool_args) if tool_args else ""
            c.print(f"[green]●[/green] [bold]{tool_name}[/bold]", end="")
            if args_str:
                c.print(f" [dim]{args_str}[/dim]")
            else:
                c.print() 
        elif tool_type == "tool_hint_end":  # 工具执行结束
            tool_output = content.get("output", "")
            if tool_output:
                lines = str(tool_output).strip().split('\n')
                c.print(f"   ↳ [dim]{lines[0]}[/dim]")
                for line in lines[1:]:
                    c.print(f"     [dim]{line}[/dim]")     

    def _write() -> None:
        ansi = _render_interactive_ansi(_render_func, console)
        print_formatted_text(ANSI(ansi), end="")
    await run_in_terminal(_write)



async def _print_interactive_progress(content: str | dict, thinking: _ThinkingSpinner | None, console) -> None:
    with thinking.pause() if thinking else nullcontext():
        await _print_progress_info(content, console)




# =============== Human In The Loop ===============
async def _hitl_approve_simple(
    tool_name: str,
    tool_args: dict,
    console: Console
) -> tuple[str, str | None]:


    if tool_name == "Bash":
        console.print(f"\n[bold]Do you want to run bash {tool_args} ? [/bold]")
    if tool_name in ["Edit", "Read", "Write"]:
        path = tool_args.get("file_path", "")
        console.print(f"\n[bold]Do you want to {tool_name} {path} ? [/bold]")

    # 使用 questionary 的 select 进行上下键选择
    from prompt_toolkit.styles import Style

    # 创建类似图片的样式
    custom_style = Style([
        ("qmark", "fg:#009688 bold"),
        ("question", ""),
        ("selected", "fg:#009688 bold"),  # 选中的选项用青色加粗
        ("pointer", "fg:#ff9800 bold"),   # 指针用橙色
        ("highlighted", "fg:#009688"),
        ("answer", "fg:#009688 bold"),
    ])

    # 使用 ask_async() 在 async 上下文中运行
    choice = await questionary.select(
        "",
        choices=[
            questionary.Choice("1. Yes", "1"),
            questionary.Choice(f"2. Yes, allow all {tool_name} during this session", "2"),
            questionary.Choice("3. No", "3"),
        ],
        style=custom_style,
        qmark="",
        pointer="➜ ",
        instruction=None
    ).ask_async()

    if choice == "1":
        return ("approve", None)
    elif choice == "2":
        return ("always_approve", None)
    elif choice == "3":
        reason = Prompt.ask(
            "Reason for rejection (optional)",
            default="",
            console=console
        )
        return ("reject", reason if reason else None)


# =============== Ask User Question - Tabbed UI ===============

# State management for tabbed UI
class _UIState(TypedDict):
    questions: list[dict]           # Original questions list
    current_tab: int                # Index of current tab (0-n, n=submit)
    selections: dict[int, int]      # {question_idx: option_idx}
    cursor_idx: int                 # Option index within current question
    answers: dict[str, str | list]  # {question_text: answer_label or list of labels}
    multi_selections: dict[int, list[int]]  # For multi-select questions
    custom_input_needed: int | None # Question index needing custom input (for "Other")
    input_mode: bool                # Whether in custom input mode
    input_buffer: str               # Current input buffer for custom input
    custom_inputs: dict[int, str]   # {question_idx: custom_input_value}


def _get_question_text(q: dict) -> str:
    """Get the question text from a question dict."""
    return q.get("question", "")


def _get_header_text(q: dict) -> str:
    """Get the header text from a question dict."""
    return q.get("header", "Question")


def _is_multi_select(q: dict) -> bool:
    """Check if a question is multi-select."""
    return q.get("multiSelect", False)


def _has_preview(options: list[dict]) -> bool:
    """Check if any option has a preview field."""
    return any(opt.get("preview") for opt in options)


def _is_question_answered(state: _UIState, q_idx: int) -> bool:
    """Check if a specific question has been answered."""
    question = state["questions"][q_idx]
    question_text = _get_question_text(question)
    return question_text in state["answers"]


def _all_questions_answered(state: _UIState) -> bool:
    """Check if all questions have been answered."""
    for q_idx, q in enumerate(state["questions"]):
        if not _is_question_answered(state, q_idx):
            return False
    return True


def _find_next_unanswered(state: _UIState) -> int | None:
    """Find the next unanswered question index."""
    for q_idx in range(len(state["questions"])):
        if not _is_question_answered(state, q_idx):
            return q_idx
    return None


def _build_progress_text(state: _UIState) -> list[tuple[str, str]]:
    """Build the progress indicator text (Step X of Y)."""
    total = len(state["questions"])
    answered = sum(1 for q_idx in range(total) if _is_question_answered(state, q_idx))
    current_step = min(state["current_tab"], total) + 1
    if current_step > total:
        current_step = total
    return [
        ("class:progress", f"Step {current_step} of {total} "),
        ("class:progress-dim", f"({answered}/{total} answered)"),
    ]


def _build_tab_bar_text(state: _UIState) -> list[tuple[str, str]]:
    """Build the horizontal tab bar with completion indicators."""
    result = []
    total_questions = len(state["questions"])

    for idx, q in enumerate(state["questions"]):
        header = _get_header_text(q)
        is_active = state["current_tab"] == idx
        is_answered = _is_question_answered(state, idx)

        if is_active:
            result.append(("class:tab-active", f" {header} "))
        elif is_answered:
            result.append(("class:tab-done", f"[{header}]"))
        else:
            result.append(("class:tab", f" {header} "))

        # Add separator except after last question
        if idx < total_questions:
            result.append(("", "  "))

    # Add submit tab
    submit_idx = total_questions
    is_submit_active = state["current_tab"] == submit_idx
    all_done = _all_questions_answered(state)

    if is_submit_active:
        result.append(("class:tab-submit", "[Submit]"))
    elif all_done:
        result.append(("class:tab-submit-ready", "[Submit]"))
    else:
        result.append(("class:tab", "[Submit]"))

    return result


def _save_answer_with_custom_input(state: _UIState, question_idx: int) -> None:
    """Save answer with custom input for a question."""
    question = state["questions"][question_idx]
    question_text = _get_question_text(question)
    options = question.get("options", [])
    is_multi = _is_multi_select(question)
    custom_input = state["custom_inputs"].get(question_idx, "")

    if is_multi:
        # Multi-select with custom input
        selected_indices = state["multi_selections"].get(question_idx, [])
        selected_labels = []
        for idx in selected_indices:
            if idx < len(options):
                label = options[idx].get("label", "")
                if label == "Other" or "其他" in label or "Other" in label:
                    selected_labels.append(f"[Custom] {custom_input}")
                elif label:
                    selected_labels.append(label)
        state["answers"][question_text] = selected_labels if selected_labels else []
    else:
        # Single select with custom input
        state["answers"][question_text] = f"[Custom] {custom_input}"


def _build_input_mode_content(state: _UIState) -> list[tuple[str, str]]:
    """Build the input mode content for custom input."""
    # Safety check
    if state["current_tab"] >= len(state["questions"]):
        state["input_mode"] = False
        return _build_question_content(state)

    question = state["questions"][state["current_tab"]]
    question_text = _get_question_text(question)
    input_buffer = state.get("input_buffer", "")

    result = [("", "\n")]
    result.append(("class:question", question_text))
    result.append(("", "\n\n"))
    result.append(("class:input-prompt", "Enter your custom answer:"))
    result.append(("", "\n"))

    # Input box
    input_line = input_buffer + "_"
    result.append(("class:input-box", "┌" + "─" * 76 + "┐"))
    result.append(("", "\n"))
    result.append(("class:input-box", "│"))
    result.append(("class:input-text", input_line.ljust(76)))
    result.append(("class:input-box", "│"))
    result.append(("", "\n"))
    result.append(("class:input-box", "└" + "─" * 76 + "┘"))
    result.append(("", "\n\n"))
    result.append(("class:input-hint", "Type your answer and press Enter to confirm"))
    result.append(("", "\n"))

    return result


def _format_preview_line(line: str) -> list[tuple[str, str]]:
    """Format a preview line with basic syntax highlighting."""
    # Check for code block markers
    if line.strip().startswith("```"):
        return [("class:preview-comment", line)]

    # Basic syntax highlighting for common patterns
    result = []
    i = 0
    while i < len(line):
        # Keywords
        matched = False
        for keyword in ["def ", "class ", "if ", "else", "return ", "import ", "from ", "async ", "await ", "function ", "const ", "let ", "var "]:
            if line[i:i+len(keyword)] == keyword:
                result.append(("class:preview-keyword", keyword))
                i += len(keyword)
                matched = True
                break

        if matched:
            continue

        # Strings
        if line[i] == '"' or line[i] == "'":
            quote = line[i]
            result.append(("class:preview-string", quote))
            i += 1
            while i < len(line) and line[i] != quote:
                result.append(("class:preview-string", line[i]))
                i += 1
            if i < len(line):
                result.append(("class:preview-string", quote))
                i += 1
        # Comments
        elif line[i:i+2] == "//" or (i > 0 and line[i-1] != ':' and line[i:i+1] == "#"):
            result.append(("class:preview-comment", line[i:]))
            break
        else:
            result.append(("class:preview-content", line[i]))
            i += 1

    return result


def _build_question_content(state: _UIState) -> list[tuple[str, str]]:
    """Build the question display and options content."""
    # Check if in input mode
    if state.get("input_mode", False):
        return _build_input_mode_content(state)

    if state["current_tab"] >= len(state["questions"]):
        # Submit tab - show summary
        return _build_submit_summary(state)

    question = state["questions"][state["current_tab"]]
    question_text = _get_question_text(question)
    options = question.get("options", [])
    is_multi = _is_multi_select(question)
    cursor = state["cursor_idx"]
    selected_indices = state["multi_selections"].get(state["current_tab"], [])
    has_preview = _has_preview(options) and not is_multi
    custom_input = state["custom_inputs"].get(state["current_tab"], "")

    result = [("", "\n")]
    result.append(("class:question", question_text))
    result.append(("", "\n\n"))

    for idx, opt in enumerate(options):
        label = opt.get("label", "")
        description = opt.get("description", "")
        is_selected = idx == cursor
        is_checked = idx in selected_indices

        # Selection indicator
        if is_multi:
            bullet = "[X]" if is_checked else "[ ]"
        else:
            bullet = ">" if is_selected else " "

        # Display label with custom input if this is "Other"/"其他" and has input
        display_label = label
        is_other_option = label == "Other" or "其他" in label or "Other" in label
        if is_other_option and custom_input:
            # Find the base label (without existing custom input if any)
            base_label = label.split(":")[0] if ":" in label else label
            display_label = f"{base_label}: {custom_input}"

        if is_selected:
            result.append(("class:option-selected", f"  {bullet} "))
            result.append(("class:option-number", f"{idx + 1}. "))
            result.append(("class:option-selected", display_label))
        else:
            result.append(("class:option", f"  {bullet} "))
            result.append(("class:option-number", f"{idx + 1}. "))
            result.append(("class:option", display_label))

        result.append(("", "\n"))

        # Don't show description for "Other"/"其他" options
        is_other_option = label == "Other" or "其他" in label or "Other" in label
        if description and not is_other_option:
            result.append(("class:description", f"     {description}"))
            result.append(("", "\n"))

        result.append(("", "\n"))

    # Add preview panel if available and an option is selected
    if has_preview and cursor < len(options):
        selected_opt = options[cursor]
        preview = selected_opt.get("preview", "")
        if preview:
            result.append(("", "\n"))
            result.append(("class:preview-border", "┌" + "─" * 76 + "┐"))
            result.append(("", "\n"))
            result.append(("class:preview-border", "│"))
            result.append(("class:preview-header", " Preview "))
            result.append(("class:preview-border", " " * 68 + "│"))
            result.append(("", "\n"))
            result.append(("class:preview-border", "├" + "─" * 76 + "┤"))
            result.append(("", "\n"))

            # Split preview into lines and format each
            for line in preview.split("\n"):
                # Format line with syntax highlighting
                formatted = _format_preview_line(line)

                # Calculate padding
                line_length = sum(len(text) for _, text in formatted)
                padding = max(0, 76 - line_length)

                result.append(("class:preview-border", "│"))
                result.extend(formatted)
                if padding > 0:
                    result.append(("", " " * padding))
                result.append(("class:preview-border", "│"))
                result.append(("", "\n"))

            result.append(("class:preview-border", "└" + "─" * 76 + "┘"))
            result.append(("", "\n"))

    return result


def _build_submit_summary(state: _UIState) -> list[tuple[str, str]]:
    """Build the summary content for the submit tab."""
    result = [("", "\n")]
    result.append(("class:title", "Summary of your choices:"))
    result.append(("", "\n\n"))

    for idx, q in enumerate(state["questions"]):
        question = _get_question_text(q)
        answer = state["answers"].get(question, "[Not answered]")

        # Format answer for display
        if isinstance(answer, list):
            if not answer:
                answer_str = "[]"
            else:
                answer_str = ", ".join(str(a) for a in answer)
        else:
            answer_str = str(answer)

        result.append(("class:question", f"{idx + 1}. {question}"))
        result.append(("", "\n"))
        result.append(("class:answer", f"   -> {answer_str}"))
        result.append(("", "\n\n"))

    result.append(("", "\n"))

    if _all_questions_answered(state):
        result.append(("class:success", "* All questions answered. Press Enter to submit."))
    else:
        result.append(("class:warning", "* Please answer all questions before submitting."))

    result.append(("", "\n\n"))
    return result


def _build_footer_text() -> list[tuple[str, str]]:
    """Build the footer with keyboard shortcuts."""
    return [
        ("", "\n"),
        ("class:footer", "up/down: Navigate  "),
        ("class:footer", "left/right: Tabs  "),
        ("class:footer", "space: Toggle multi-select  "),
        ("class:footer", "enter: Confirm  "),
        ("class:footer", "esc: Cancel"),
    ]


def _handle_key_left(event, state: _UIState, app) -> None:
    """Handle left arrow key - previous tab."""
    # Exit input mode if navigating
    if state.get("input_mode", False):
        state["input_mode"] = False
        state["input_buffer"] = ""

    state["current_tab"] = max(0, state["current_tab"] - 1)
    if state["current_tab"] < len(state["questions"]):
        saved_selection = state["selections"].get(state["current_tab"])
        state["cursor_idx"] = saved_selection if saved_selection is not None else 0
    app.invalidate()


def _handle_key_right(event, state: _UIState, app) -> None:
    """Handle right arrow key - next tab."""
    # Exit input mode if navigating
    if state.get("input_mode", False):
        state["input_mode"] = False
        state["input_buffer"] = ""

    state["current_tab"] = min(len(state["questions"]), state["current_tab"] + 1)
    if state["current_tab"] < len(state["questions"]):
        saved_selection = state["selections"].get(state["current_tab"])
        state["cursor_idx"] = saved_selection if saved_selection is not None else 0
    app.invalidate()


def _handle_key_up(event, state: _UIState, app) -> None:
    """Handle up arrow key - previous option."""
    if state.get("input_mode", False):
        return  # Don't move cursor in input mode
    if state["current_tab"] < len(state["questions"]):
        state["cursor_idx"] = max(0, state["cursor_idx"] - 1)
    app.invalidate()


def _handle_key_down(event, state: _UIState, app) -> None:
    """Handle down arrow key - next option."""
    if state.get("input_mode", False):
        return  # Don't move cursor in input mode
    if state["current_tab"] < len(state["questions"]):
        options = state["questions"][state["current_tab"]].get("options", [])
        state["cursor_idx"] = min(len(options) - 1, state["cursor_idx"] + 1)
    app.invalidate()


def _handle_key_enter(event, state: _UIState, app) -> None:
    """Handle enter key - confirm selection or submit."""
    # If in input mode, finish input and move to next question
    if state.get("input_mode", False):
        input_text = state.get("input_buffer", "")
        current_tab = state["current_tab"]
        state["custom_inputs"][current_tab] = input_text
        state["input_mode"] = False
        state["input_buffer"] = ""

        # Save the answer with custom input
        _save_answer_with_custom_input(state, current_tab)

        # Move to next unanswered question
        next_unanswered = _find_next_unanswered(state)
        if next_unanswered is not None:
            state["current_tab"] = next_unanswered
            saved_selection = state["selections"].get(next_unanswered)
            state["cursor_idx"] = saved_selection if saved_selection is not None else 0
        app.invalidate()
        return

    if state["current_tab"] == len(state["questions"]):
        # Submit tab - only submit if all questions are answered
        if _all_questions_answered(state):
            app.exit(result=state["answers"])
        # Else stay on submit tab (user can see warning in summary)
    else:
        # Check if "Other" is selected for immediate input
        question = state["questions"][state["current_tab"]]
        options = question.get("options", [])
        is_multi = _is_multi_select(question)
        cursor = state["cursor_idx"]

        should_prompt_custom = False
        if is_multi:
            selected_indices = state["multi_selections"].get(state["current_tab"], [])
            for idx in selected_indices:
                if idx < len(options):
                    label = options[idx].get("label", "")
                    if label == "Other" or "其他" in label or "Other" in label:
                        should_prompt_custom = True
                        break
        else:
            if cursor < len(options):
                label = options[cursor].get("label", "")
                if label == "Other" or "其他" in label or "Other" in label:
                    should_prompt_custom = True

        if should_prompt_custom:
            # Enter input mode instead of exiting
            state["input_mode"] = True
            state["input_buffer"] = ""
            # Mark the selection
            if not is_multi:
                state["selections"][state["current_tab"]] = cursor
            else:
                state["selections"][state["current_tab"]] = cursor
            app.invalidate()
        else:
            # Normal confirmation
            _confirm_selection(state, app)
    app.invalidate()


def _handle_key_space(event, state: _UIState, app) -> None:
    """Handle space key - toggle multi-select option."""
    if state.get("input_mode", False):
        return  # Allow space in input mode for typing
    if state["current_tab"] >= len(state["questions"]):
        return

    question = state["questions"][state["current_tab"]]
    is_multi = _is_multi_select(question)

    if is_multi:
        cursor = state["cursor_idx"]
        selected = state["multi_selections"].setdefault(state["current_tab"], [])
        if cursor in selected:
            selected.remove(cursor)
        else:
            selected.append(cursor)
        state["selections"][state["current_tab"]] = cursor
    app.invalidate()


def _handle_key_escape(event, state: _UIState, app) -> None:
    """Handle escape key - cancel."""
    # If in input mode, exit input mode
    if state.get("input_mode", False):
        state["input_mode"] = False
        state["input_buffer"] = ""
        app.invalidate()
    else:
        app.exit(result={})


def _confirm_selection(state: _UIState, app) -> None:
    """Confirm the current selection for the active question."""
    question = state["questions"][state["current_tab"]]
    options = question.get("options", [])
    is_multi = _is_multi_select(question)
    cursor = state["cursor_idx"]

    question_text = _get_question_text(question)

    if is_multi:
        # For multi-select, Enter confirms all selections and moves to next question
        selected_indices = state["multi_selections"].get(state["current_tab"], [])

        # Collect selected labels (skip "Other"/"其他" as they're handled in input mode)
        selected_labels = []
        for idx in selected_indices:
            if idx < len(options):
                label = options[idx].get("label", "")
                is_other = label == "Other" or "其他" in label or "Other" in label
                if label and not is_other:
                    selected_labels.append(label)

        # Save as list (empty list if no selections)
        state["answers"][question_text] = selected_labels if selected_labels else []
    else:
        # Single select - confirm and move to next
        state["selections"][state["current_tab"]] = cursor

        selected_opt = options[cursor]
        label = selected_opt.get("label", "")

        # Save the answer (skip "Other"/"其他" as they're handled in input mode)
        is_other = label == "Other" or "其他" in label or "Other" in label
        if label and not is_other:
            state["answers"][question_text] = label

    # Move to next unanswered question
    next_unanswered = _find_next_unanswered(state)
    if next_unanswered is not None:
        state["current_tab"] = next_unanswered
        saved_selection = state["selections"].get(next_unanswered)
        state["cursor_idx"] = saved_selection if saved_selection is not None else 0


# =============== Ask User Question ===============
async def _present_user_questions(
    questions: list[dict],
    console: Console
) -> dict:
    """
    Present questions to the user using a tabbed CLI interface.

    Features:
    - Tabbed navigation between questions
    - Progress indicator showing current step
    - Arrow key navigation for questions and options
    - Preview support for options with preview field
    - Submit tab for reviewing and submitting answers
    """
    from prompt_toolkit.layout import Layout, HSplit
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.application import Application
    from prompt_toolkit.styles import Style
    from prompt_toolkit.keys import Keys

    if not questions:
        return {}

    # Add "Other" option to each question if not already present
    for q in questions:
        options = q.get("options", [])
        has_other = any(
            opt.get("label") == "Other" or
            "其他" in opt.get("label", "") or
            "Other" in opt.get("label", "")
            for opt in options
        )
        if not has_other:
            options.append({"label": "Other", "description": "Provide custom input"})

    # Initialize state
    state: _UIState = {
        "questions": questions,
        "current_tab": 0,
        "selections": {},
        "cursor_idx": 0,
        "answers": {},
        "multi_selections": {},
        "custom_input_needed": None,
        "input_mode": False,
        "input_buffer": "",
        "custom_inputs": {},
    }

    # Create content getter functions that capture state
    def get_progress():
        return _build_progress_text(state)

    def get_tab_bar():
        return _build_tab_bar_text(state)

    def get_content():
        return _build_question_content(state)

    def get_footer():
        return _build_footer_text()

    # Create layout first
    layout = Layout(HSplit([
        Window(height=1, content=FormattedTextControl(get_progress)),
        Window(height=1, content=FormattedTextControl(get_tab_bar)),
        Window(content=FormattedTextControl(get_content)),
        Window(height=1, content=FormattedTextControl(get_footer)),
    ]))

    # Create app reference (will be set after Application is created)
    app_ref = {"app": None}

    # Create key bindings with specific handlers
    kb = KeyBindings()

    @kb.add(Keys.Left)
    def _(event):
        _handle_key_left(event, state, app_ref["app"])

    @kb.add(Keys.Right)
    def _(event):
        _handle_key_right(event, state, app_ref["app"])

    @kb.add(Keys.Up)
    def _(event):
        _handle_key_up(event, state, app_ref["app"])

    @kb.add(Keys.Down)
    def _(event):
        _handle_key_down(event, state, app_ref["app"])

    @kb.add(Keys.Enter)
    def _(event):
        _handle_key_enter(event, state, app_ref["app"])

    @kb.add(" ")
    def _(event):
        _handle_key_space(event, state, app_ref["app"])

    @kb.add(Keys.Escape)
    def _(event):
        _handle_key_escape(event, state, app_ref["app"])

    @kb.add(Keys.Backspace)
    def _(event):
        if state.get("input_mode", False):
            buffer = state.get("input_buffer", "")
            state["input_buffer"] = buffer[:-1]
            app_ref["app"].invalidate()

    # Catch-all for character input in input mode
    @kb.add("<any>")
    def _(event):
        # Only handle in input mode and for printable characters
        if state.get("input_mode", False):
            data = event.data
            # Check if it's a printable character (single char, not a special key)
            if isinstance(data, str) and len(data) == 1 and data.isprintable():
                buffer = state.get("input_buffer", "")
                state["input_buffer"] = buffer + data
                app_ref["app"].invalidate()

    # Define dark mode style
    style = Style([
        # Progress
        ("progress", "fg:#4a9eff bold"),
        ("progress-dim", "fg:#888888"),

        # Tab bar
        ("tab", "fg:#666666"),
        ("tab-active", "fg:#ffffff bg:#4a9eff bold"),
        ("tab-done", "fg:#00ff00"),
        ("tab-submit", "fg:#ffffff bg:#00aa00"),
        ("tab-submit-ready", "fg:#00ff00 bg:#006600"),

        # Question and title
        ("question", "fg:#ffffff bold"),
        ("title", "fg:#ffffff bold"),
        ("answer", "fg:#4a9eff"),
        ("warning", "fg:#ff9800 bold"),
        ("success", "fg:#00ff00 bold"),

        # Options
        ("option", "fg:#cccccc"),
        ("option-selected", "fg:#ffffff bg:#4a9eff bold"),
        ("option-number", "fg:#4a9eff bold"),
        ("description", "fg:#888888"),

        # Preview
        ("preview-header", "fg:#4a9eff bold"),
        ("preview-border", "fg:#4a9eff"),
        ("preview-content", "fg:#e0e0e0"),
        ("preview-code", "fg:#00ff00"),
        ("preview-keyword", "fg:#ff79c6"),
        ("preview-string", "fg:#f1fa8c"),
        ("preview-comment", "fg:#6272a4"),

        # Input mode
        ("input-prompt", "fg:#4a9eff bold"),
        ("input-box", "fg:#4a9eff"),
        ("input-text", "fg:#ffffff"),
        ("input-hint", "fg:#888888"),

        # Footer
        ("footer", "fg:#666666"),
    ])

    # Create application
    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=False,
        mouse_support=False,
    )

    # Set app reference for key handlers
    app_ref["app"] = app

    # Run the application (no loop needed since input is handled internally)
    try:
        result = await app.run_async()
        return result if result is not None else {}
    except Exception as e:
        # Fall back to questionary-based implementation if prompt_toolkit fails
        raise e


async def _present_user_questions_fallback(
    questions: list[dict],
    console: Console
) -> dict:
    """Fallback implementation using questionary."""
    custom_style = Style([
        ("qmark", "fg:#673ab7 bold"),
        ("question", "fg:#673ab7 bold"),
        ("selected", "fg:#673ab7 bold"),
        ("pointer", "fg:#ff9800 bold"),
        ("highlighted", "fg:#673ab7"),
        ("answer", "fg:#673ab7 bold"),
    ])

    answers_dict = {}

    for q in questions:
        header = q.get("header", "")
        options = q.get("options", [])
        multi_select = q.get("multiSelect", False)

        console.print()
        console.print(f"[bold cyan]⬡ {header}[/bold cyan]")

        # 检查是否有选项具有预览（仅适用于单选）
        has_preview = any(opt.get("preview") for opt in options) and not multi_select

        if has_preview:
            # 并排布局以便预览
            answer = await _ask_question_with_preview(q, console, custom_style)
        else:
            # 标准布局
            answer = await _ask_question_standard(q, console, custom_style)

        # 合并答案到字典中
        answers_dict.update(answer)

    return answers_dict


async def _ask_question_standard(
    q: dict,
    console: Console,
    style: Style,
) -> dict:
    question_text = q.get("question", "")
    options = q.get("options", [])
    multi_select = q.get("multiSelect", False)

    # 构建选项
    choices = []
    for opt in options:
        label = opt.get("label", "")
        description = opt.get("description", "")
        display_text = f"{label}: {description}"
        choices.append(questionary.Choice(display_text, label))

    # 添加other选项
    choices.append(questionary.Choice("Other (provide custom input)", "__other__"))

    if multi_select:
        # Multi-select using checkbox
        selected = await questionary.checkbox(
            question_text,
            choices=choices,
            style=style,
            instruction="(Use arrow keys, space to select, enter to submit)"
        ).ask_async()

        # Handle None (user cancelled)
        if selected is None:
            return {question_text: []}

        # Handle "Other" option
        if "__other__" in selected:
            selected.remove("__other__")
            custom_input = Prompt.ask(
                "\nYour custom answer",
                console=console
            )
            selected.append(f"[Custom] {custom_input}")

        return {question_text: selected if selected else []}
    else:
        # Single-select using select
        selected = await questionary.select(
            question_text,
            choices=choices,
            style=style,
            instruction="(Use arrow keys, enter to select)"
        ).ask_async()

        # Handle None (user cancelled)
        if selected is None:
            return {question_text: ""}

        if selected == "__other__":
            # Custom input
            custom_input = Prompt.ask(
                "\nYour answer",
                console=console
            )
            return {question_text: f"[Custom] {custom_input}"}
        else:
            return {question_text: selected}


async def _ask_question_with_preview(
    q: dict,
    console: Console,
    style: Style,
) -> dict:
    """
    Ask a question with side-by-side preview layout.

    Returns:
        Dictionary with question text as key and answer as value
    """
    question_text = q.get("question", "")
    options = q.get("options", [])

    # Build choices without descriptions (descriptions shown in preview)
    choices = []
    preview_map = {}
    for i, opt in enumerate(options):
        label = opt.get("label", "")
        description = opt.get("description", "")
        preview = opt.get("preview", "")
        # Use index as value to map to preview
        choices.append(questionary.Choice(f"{i+1}. {label}", str(i)))
        preview_map[str(i)] = {
            "label": label,
            "description": description,
            "preview": preview
        }

    # Add "Other" option (no preview)
    choices.append(questionary.Choice(f"{len(options)+1}. Other (provide custom input)", "__other__"))

    # Show the question
    console.print(f"[dim]{question_text}[/dim]")

    # Let user select
    selected = await questionary.select(
        "Select an option (preview will be shown on the right)",
        choices=choices,
        style=style,
        instruction="(Use arrow keys to see previews, enter to select)"
    ).ask_async()

    # Handle None (user cancelled)
    if selected is None:
        return {question_text: ""}

    if selected == "__other__":
        # Custom input
        custom_input = Prompt.ask(
            "\nYour answer",
            console=console
        )
        return {question_text: f"[Custom] {custom_input}"}
    else:
        # Show selected option with its description and preview
        opt_data = preview_map.get(selected, {})
        console.print()
        console.print(f"[bold]Selected:[/bold] {opt_data.get('label', '')}")
        console.print(f"[dim]{opt_data.get('description', '')}[/dim]")

        if opt_data.get("preview"):
            console.print()
            console.print(Panel(
                Markdown(opt_data["preview"]),
                title="[bold]Preview[/bold]",
                border_style="dim"
            ))

        return {question_text: opt_data.get("label", "")}
