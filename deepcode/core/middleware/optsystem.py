import subprocess
from pathlib import Path
from typing import Annotated, Optional, Literal

from langchain.agents.middleware import AgentMiddleware
from langchain_core.tools import tool, BaseTool
from deepcode.core.manager.filesystem import FileSystemManager
from deepcode.core.prompt.tools.bash import bash_desc as BASH_DESC
from deepcode.core.prompt.tools.read import read_desc as READ_DESC
from deepcode.core.prompt.tools.write import write_desc as WRITE_DESC
from deepcode.core.prompt.tools.glob import glob_desc as GLOB_DESC
from deepcode.core.prompt.tools.grep import grep_desc as GREP_DESC
from deepcode.core.prompt.tools.edit import edit_desc as EDIT_DESC



class OptSystemMiddleware(AgentMiddleware):
    """ Bash and file-system opt"""

    def __init__(self, workdir: Path):
        self.workdir = workdir if isinstance(workdir, Path) else Path(workdir)

        self.filesys = FileSystemManager(self.workdir)
        self.tools = [
            self._create_bash(),
            self._create_read(),
            self._create_write(),
            self._create_edit(),
            self._create_glob(),
            self._create_grep()
        ]


    def _create_bash(self) -> BaseTool:
        @tool(name_or_callable="Bash",description=BASH_DESC)
        def bash(command: Annotated[str, "The command to execute"]) -> str:
            dangerous = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]
            if any(d in command for d in dangerous):
                return "Error: Dangerous command"
            try:
                r = subprocess.run(
                    command, shell=True, cwd=str(self.workdir), capture_output=True,
                    text=True, timeout=120
                )
                out = (r.stdout + r.stderr).strip()
                return out[:50000] if out else "(no output)"
            except subprocess.TimeoutExpired:
                return "Error: Timeout(120s)"
        return bash
    def _create_read(self) -> BaseTool:
        @tool(name_or_callable="Read",description=READ_DESC)
        def read(
            file_path: Annotated[str, "The absolute path to the file to read"],
            offset: Annotated[Optional[int], "The line number to start reading from. Only provide if the file is too large to read at once"] = None, 
            limit: Annotated[Optional[int], "The number of lines to read. Only provide if the file is too large to read at once."] = None
        ) -> str:
            return self.filesys.read(file_path, offset, limit)
        return read
    
    def _create_write(self) -> BaseTool:
        @tool(name_or_callable="Write", description=WRITE_DESC)
        def write(
            file_path: Annotated[str, "The absolute path to the file to write (must be absolute, not relative)"], 
            content: Annotated[str, "The content to write to the file"]
        ) -> str:
            return self.filesys.write(file_path, content)
        return write

    def _create_edit(self) -> BaseTool:
        @tool(name_or_callable="Edit",description=EDIT_DESC)
        def edit(
            file_path: Annotated[str, "The absolute path to the file to modify"], 
            old_string: Annotated[str, "The text to replace"], 
            new_string: Annotated[str, "The text to replace it with (must be different from old_string)"],
            replace_all: Annotated[bool, "Replace all occurrences of old_string (default false)"] = False
        ) -> str:
            return self.filesys.edit(file_path, old_string, new_string, replace_all)
        return edit
    
    def _create_glob(self) -> BaseTool:
        @tool(name_or_callable="Glob", description=GLOB_DESC)
        def glob(
            pattern: Annotated[str, "The glob pattern to match files against"],
            path: Annotated[Optional[str], "The directory to search in. If not specified, the current working directory will be used. IMPORTANT: Omit this field to use the default directory. DO NOT enter \"undefined\" or \"null\" - simply omit it for the default behavior. Must be a valid directory path if provided."] = None
        ) -> list[str]:
            return self.filesys.glob(pattern, path)
        return glob
    
    def _create_grep(self) -> BaseTool:
        @tool(name_or_callable="Grep", description=GREP_DESC)
        def grep(
            pattern: Annotated[str, "The regular expression pattern to search for in file contents"],
            path: Annotated[Optional[str], "File or directory to search in (rg PATH). Defaults to current working directory."] = None,
            glob: Annotated[Optional[str], "Glob pattern to filter files (e.g. \"*.js\", \"*.{ts,tsx}\") - maps to rg --glob"] = None,
            output_mode: Annotated[Literal["content", "files_with_matches", "count"], "Output mode: \"content\" shows matching lines (supports -A/-B/-C context, -n line numbers, head_limit), \"files_with_matches\" shows file paths (supports head_limit), \"count\" shows match counts (supports head_limit). Defaults to \"files_with_matches\"."] = "files_with_matches",
            context: Annotated[Optional[int], "Number of lines of context to include around matches. Maps to rg --context"] = None,
            _C: Annotated[Optional[int], "Alias for context"] = None,
            _A: Annotated[Optional[int], "Number of lines to show after each match (rg -A). Requires output_mode: \"content\", ignored otherwise."] = None,
            _B: Annotated[Optional[int], "Number of lines to show before each match (rg -B). Requires output_mode: \"content\", ignored otherwise."] = None,
            _n: Annotated[bool, "Show line numbers in output (rg -n). Requires output_mode: \"content\", ignored otherwise. Defaults to true."] = True,
            _i: Annotated[bool, "Case insensitive search (rg -i)"] = False,
            type: Annotated[Optional[str], "File type to search (rg --type). Common types: js, py, rust, go, java, etc."] = None,
            head_limit: Annotated[int, "Limit output to first N lines/entries. Defaults to 250. Pass 0 for unlimited."] = 250,
            offset: Annotated[int, "Skip first N lines/entries before applying head_limit. Defaults to 0."] = 0,
            multiline: Annotated[bool, "Enable multiline mode where . matches newlines (rg -U --multiline-dotall). Default: false."] = False
        ) -> str | list[str]:
            return self.filesys.grep(pattern, path, glob, output_mode, context, _C, _A, _B, _n, _i, head_limit, offset, multiline, type)
        return grep