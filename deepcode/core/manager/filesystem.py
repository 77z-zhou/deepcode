import platform
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Literal


class FileSystemManager:
    """文件系统管理器 - 提供安全的文件操作，严格限制在 workspace 内"""

    # 安全限制常量
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_SCAN_FILES = 10000
    MAX_REGEX_TIME = 5
    MAX_LINE_LENGTH = 10000

    def __init__(self, workspace: Path):
        self.workspace = Path(workspace).resolve()
        self._ripgrep_available = shutil.which("rg") is not None
        self._is_windows = platform.system() == "Windows"

    # ==================== 私有方法 ====================

    def _safe_path(self, path: str) -> Path:
        """确保路径在 workspace 范围内"""
        p = Path(path)
        if not p.is_absolute():
            p = self.workspace / p
        p = p.resolve()
        if not p.is_relative_to(self.workspace):
            raise ValueError(f"Path escapes workspace: {path}")
        return p

    def _is_safe_file(self, path: Path) -> bool:
        """检查文件是否安全（非符号链接，且在 workspace 内）"""
        try:
            return not path.is_symlink() and path.resolve().is_relative_to(self.workspace)
        except (OSError, ValueError):
            return False

    def _is_absolute_glob(self, pattern: str) -> bool:
        """检查 glob 模式是否为绝对路径（跨平台）"""
        return pattern.startswith("/") or (self._is_windows and len(pattern) > 1 and pattern[1] == ":")

    def _is_safe_regex(self, pattern: str) -> bool:
        """检查正则表达式是否安全（防止 ReDoS 攻击）"""
        # 危险模式检测
        dangerous = [r"((\w+)*)+\$", r"(a+)+", r"([a-zA-Z]+)*a", r"(x+)+y", r"(.+)*[']", r"(.*)*\["]
        if any(d in pattern for d in dangerous):
            return False

        try:
            regex = re.compile(pattern, re.IGNORECASE)
            for test in ["a" * 50, "a" * 100 + "b", "x" * 50 + "y" * 50]:
                start = time.time()
                regex.search(test)
                if time.time() - start > self.MAX_REGEX_TIME / 10:
                    return False
            return True
        except re.error:
            return False

    def _validate_glob(self, pattern: str) -> bool:
        """验证 glob 模式安全性"""
        return ".." not in pattern and not self._is_absolute_glob(pattern)

    def _filter_workspace_paths(self, lines: list[str], has_colon: bool) -> list[str]:
        """过滤出 workspace 内的路径"""
        filtered = []
        for line in lines:
            file_path = line.split(":")[0] if has_colon else line
            try:
                if Path(file_path).is_relative_to(self.workspace):
                    filtered.append(line)
            except (ValueError, OSError):
                pass
        return filtered

    def _grep_fallback(
        self,
        pattern: str,
        search_path: Path,
        glob_pattern: Optional[str],
        output_mode: str,
        ignore_case: bool,
        multiline: bool,
        file_type: Optional[str]
    ) -> str | list[str]:
        """ripgrep 不可用时的纯 Python 实现（multiline 参数忽略）"""

        if not self._is_safe_regex(pattern):
            return f"Error: Unsafe regex pattern: {pattern}"

        try:
            regex = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
        except re.error:
            return f"Error: Invalid regex pattern: {pattern}"

        # 收集文件
        try:
            if glob_pattern:
                if not self._validate_glob(glob_pattern):
                    return []
                files = list(search_path.glob(glob_pattern))
            elif file_type:
                files = list(search_path.rglob(f"*.{file_type}"))
            else:
                files = list(search_path.rglob("*"))

            safe_files = [f for f in files[:self.MAX_SCAN_FILES] if f.is_file() and self._is_safe_file(f)]
        except Exception:
            return []
        
        # 搜索
        results = []
        for f in safe_files:
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()

                if output_mode == "files_with_matches":
                    if any(regex.search(line) for line in lines):
                        results.append(str(f))
                elif output_mode == "count":
                    count = sum(1 for line in lines if regex.search(line))
                    if count > 0:
                        results.append(f"{f}:{count}")
                else:  # content
                    for i, line in enumerate(lines, 1):
                        if regex.search(line):
                            results.append(f"{f}:{i}:{line}")
                            if len(results) >= 250:
                                break
            except Exception:
                pass
            if len(results) >= 250:
                break

        return results if output_mode != "content" else "\n".join(results)

    # ==================== 公共方法 ====================

    def read(self, file_path: str, offset: Optional[int] = None, limit: Optional[int] = None) -> str:
        """读取文件内容，返回带行号的格式"""
        try:
            path = self._safe_path(file_path)

            if not self._is_safe_file(path):
                return f"Error: Access denied: {file_path}"
            if not path.exists():
                return f"Error: File not found: {file_path}"
            if not path.is_file():
                return f"Error: Not a file: {file_path}"
            if path.stat().st_size > self.MAX_FILE_SIZE:
                return f"Error: File too large"

            lines = path.read_text(encoding="utf-8").splitlines()

            # 应用 offset 和 limit
            start = max(0, (offset or 1) - 1)
            end = start + limit if limit else len(lines)
            lines = lines[start:end]

            # 默认最多 2000 行
            if not limit and len(lines) > 2000:
                lines = lines[:2000]
                truncation = f"\n... ({len(lines) - 2000} more lines)"
            else:
                truncation = ""

            # 添加行号
            result = [f"{i + start + 1}\t{line[:self.MAX_LINE_LENGTH]}" for i, line in enumerate(lines)]
            return "\n".join(result) + truncation

        except UnicodeDecodeError:
            return f"Error: Cannot decode file: {file_path}"
        except Exception as e:
            return f"Error: {e}"

    def write(self, file_path: str, content: str) -> str:
        """写入文件（覆盖模式）"""
        try:
            path = self._safe_path(file_path)

            if len(content) > self.MAX_FILE_SIZE:
                return f"Error: Content too large"
            if path.exists() and not self._is_safe_file(path):
                return f"Error: Access denied: {file_path}"

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return f"Successfully wrote {len(content)} bytes to {file_path}"

        except Exception as e:
            return f"Error: {e}"

    def edit(self, file_path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        """编辑文件（精确字符串替换）"""
        try:
            path = self._safe_path(file_path)

            if not path.exists():
                return f"Error: File not found: {file_path}"
            if not self._is_safe_file(path):
                return f"Error: Access denied: {file_path}"
            if path.stat().st_size > self.MAX_FILE_SIZE:
                return f"Error: File too large"

            content = path.read_text(encoding="utf-8")

            if old_string not in content:
                return f"Error: '{old_string}' not found in {file_path}"
            if not replace_all and content.count(old_string) > 1:
                return f"Error: '{old_string}' appears multiple times. Use replace_all=True"

            # -1:替换所有  1: 只替换第一个
            new_content = content.replace(old_string, new_string, -1 if replace_all else 1)
            path.write_text(new_content, encoding="utf-8")
            return f"Successfully replaced {content.count(old_string)} occurrence(s) in {file_path}"

        except Exception as e:
            return f"Error: {e}"

    def glob(self, pattern: str, path: Optional[str] = None) -> list[str]:
        """文件模式匹配"""
        try:
            search_path = self._safe_path(path) if path else self.workspace
            if not search_path.exists() or not self._validate_glob(pattern):
                return []

            files = [
                str(f) for f in search_path.glob(pattern)
                if f.is_file() and self._is_safe_file(f)
            ]
            files.sort(key=lambda x: Path(x).stat().st_mtime, reverse=True)
            return files

        except Exception:
            return []

    def grep(
        self,
        pattern: str,
        path: Optional[str] = None,
        glob: Optional[str] = None,
        output_mode: Literal["content", "files_with_matches", "count"] = "files_with_matches",
        context: Optional[int] = None,
        _C: Optional[int] = None,
        _A: Optional[int] = None,
        _B: Optional[int] = None,
        _n: bool = True,
        _i: bool = False,
        head_limit: int = 250,
        offset: int = 0,
        multiline: bool = False,
        type: Optional[str] = None
    ) -> str | list[str]:
        """搜索文件内容"""

        try:
            search_path = self._safe_path(path) if path else self.workspace

            if not self._is_safe_regex(pattern): # 危险正则过滤
                return f"Error: Unsafe regex pattern: {pattern}"
            if glob and not self._validate_glob(glob):
                return f"Error: Invalid glob pattern"

            # ripgrep 不可用时使用 fallback
            if not self._ripgrep_available:
                return self._grep_fallback(pattern, search_path, glob, output_mode, _i, multiline, type)

            # 构建 ripgrep 命令
            cmd = ["rg", pattern, str(search_path)]

            if output_mode == "files_with_matches":
                cmd.append("-l")
            elif output_mode == "count":
                cmd.append("-c")

            # 上下文参数只在 content 模式下生效
            if output_mode == "content":
                if _C or context:
                    cmd.extend(["-C", str(_C or context or 0)])
                else:
                    if _B:
                        cmd.extend(["-B", str(_B)])
                    if _A:
                        cmd.extend(["-A", str(_A)])

            if not _n and output_mode == "content":
                cmd.append("-N")
            if _i:
                cmd.append("-i")
            if multiline:
                cmd.extend(["-U", "--multiline-dotall"])
            if type:
                cmd.extend(["-t", type])
            if glob:
                cmd.extend(["--glob", glob])

            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
                output = result.stdout.strip()
                if not output:
                    return [] if output_mode != "content" else ""

                lines = output.split("\n")[offset:offset + head_limit] if head_limit else output.split("\n")

                # 过滤 workspace 内的路径
                filtered = self._filter_workspace_paths(lines, output_mode == "content" or output_mode == "count")
                return "\n".join(filtered) if output_mode == "content" else filtered

            except (subprocess.TimeoutExpired, Exception):
                return self._grep_fallback(pattern, search_path, glob, output_mode, _i, multiline, type)

        except Exception as e:
            return f"Error: {e}"
