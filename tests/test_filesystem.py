"""
FileSystemManager 测试

测试文件系统的安全性和功能性，确保所有操作都限制在 workspace 内。
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from deepcode.core.manager.filesystem import FileSystemManager


@pytest.fixture
def workspace():
    """创建临时工作目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def fs(workspace):
    """创建 FileSystemManager 实例"""
    return FileSystemManager(workspace)


class TestRead:
    """测试 read 方法"""

    def test_read_normal_file(self, fs, workspace):
        """测试读取普通文件"""
        test_file = workspace / "test.txt"
        test_file.write_text("hello\nworld\npython", encoding="utf-8")

        result = fs.read(str(test_file))
        assert "hello" in result
        assert "world" in result
        assert "python" in result

    def test_read_with_limit(self, fs, workspace):
        """测试读取指定行数"""
        test_file = workspace / "test.txt"
        test_file.write_text("line1\nline2\nline3\nline4\nline5", encoding="utf-8")

        result = fs.read(str(test_file), limit=2)
        lines = result.split("\n")
        assert len(lines) == 2
        assert "line1" in result
        assert "line2" in result

    def test_read_with_offset(self, fs, workspace):
        """测试从指定行开始读取"""
        test_file = workspace / "test.txt"
        test_file.write_text("line1\nline2\nline3\nline4", encoding="utf-8")
        result = fs.read(str(test_file), offset=2)
        assert "line2" in result

    def test_read_nonexistent_file(self, fs, workspace):
        """测试读取不存在的文件"""
        test_file = workspace /"nonexistent/file.txt"
        result = fs.read(test_file)
        assert "Error: File not found" in result

    def test_read_path_traversal_blocked(self, fs, workspace):
        """测试路径遍历攻击被阻止"""
        result = fs.read("../../../etc/passwd")
        assert "Error" in result or "escapes workspace" in result

    def test_read_line_numbers(self, fs, workspace):
        """测试返回内容带行号"""
        test_file = workspace / "test.txt"
        test_file.write_text("hello\nworld", encoding="utf-8")

        result = fs.read(str(test_file))
        assert "1\thello" in result
        assert "2\tworld" in result


class TestWrite:
    """测试 write 方法"""

    def test_write_new_file(self, fs, workspace):
        """测试写入新文件"""
        test_file = workspace / "new.txt"
        result = fs.write(str(test_file), "hello world")

        assert test_file.exists()
        assert test_file.read_text() == "hello world"
        assert "Success" in result

    def test_write_creates_directory(self, fs, workspace):
        """测试自动创建父目录"""
        test_file = workspace / "subdir" / "nested" / "file.txt"
        result = fs.write(str(test_file), "content")

        assert test_file.exists()
        assert test_file.parent.exists()

    def test_write_overwrite_existing(self, fs, workspace):
        """测试覆盖已存在的文件"""
        test_file = workspace / "test.txt"
        test_file.write_text("old content")

        fs.write(str(test_file), "new content")
        assert test_file.read_text() == "new content"

    def test_write_large_content_blocked(self, fs):
        """测试写入超大内容被阻止"""
        large_content = "x" * (11 * 1024 * 1024)  # 11MB
        result = fs.write("test.txt", large_content)
        assert "too large" in result

    def test_write_path_traversal_blocked(self, fs, workspace):
        """测试路径遍历攻击被阻止"""
        result = fs.write("../../../etc/evil.txt", "malicious")
        assert "Error" in result


class TestEdit:
    """测试 edit 方法"""

    def test_edit_single_occurrence(self, fs, workspace):
        """测试替换单个匹配项"""
        test_file = workspace / "test.txt"
        test_file.write_text("hello world")

        result = fs.edit(str(test_file), "world", "python")
        assert test_file.read_text() == "hello python"
        assert "Success" in result

    def test_edit_replace_all(self, fs, workspace):
        """测试替换所有匹配项"""
        test_file = workspace / "test.txt"
        test_file.write_text("cat cat cat")

        result = fs.edit(str(test_file), "cat", "dog", replace_all=True)
        assert test_file.read_text() == "dog dog dog"

    def test_edit_multiple_without_replace_all_fails(self, fs, workspace):
        """测试多个匹配但不启用 replace_all 时失败"""
        test_file = workspace / "test.txt"
        test_file.write_text("cat cat")

        result = fs.edit(str(test_file), "cat", "dog")
        assert "appears multiple times" in result

    def test_edit_nonexistent_string(self, fs, workspace):
        """测试替换不存在的字符串"""
        test_file = workspace / "test.txt"
        test_file.write_text("hello")

        result = fs.edit(str(test_file), "world", "python")
        assert "not found" in result

    def test_edit_nonexistent_file(self, fs):
        """测试编辑不存在的文件"""
        result = fs.edit("nonexistent.txt", "old", "new")
        assert "File not found" in result


class TestGlob:
    """测试 glob 方法"""

    def test_glob_simple_pattern(self, fs, workspace):
        """测试简单模式匹配"""
        (workspace / "test1.py").write_text("")
        (workspace / "test2.py").write_text("")
        (workspace / "test.txt").write_text("")

        result = fs.glob("*.py")
        assert len(result) == 2
        assert all(f.endswith(".py") for f in result)

    def test_glob_recursive_pattern(self, fs, workspace):
        """测试递归模式匹配"""
        (workspace / "subdir").mkdir()
        (workspace / "subdir" / "nested.py").write_text("")
        (workspace / "top.py").write_text("")

        result = fs.glob("**/*.py")
        print(result)
        assert len(result) == 2

    def test_glob_in_subdirectory(self, fs, workspace):
        """测试在子目录中搜索"""
        (workspace / "subdir").mkdir()
        (workspace / "subdir" / "test.py").write_text("")
        (workspace / "test.txt").write_text("")

        result = fs.glob("*.py", "subdir")
        assert len(result) == 1

    def test_glob_absolute_path_blocked(self, fs):
        """测试绝对路径模式被阻止"""
        result = fs.glob("/etc/*")
        assert result == []

    def test_glob_windows_absolute_path_blocked(self, fs):
        """测试 Windows 绝对路径被阻止"""
        result = fs.glob("C:/Windows/*")
        assert result == []

    def test_glob_with_path_traversal_blocked(self, fs):
        """测试路径遍历被阻止"""
        result = fs.glob("../**/*.py")
        assert result == []

    def test_glob_returns_only_files(self, fs, workspace):
        """测试只返回文件，不包含目录"""
        (workspace / "file.py").write_text("")
        (workspace / "dir.py").mkdir()

        result = fs.glob("*.py")
        assert len(result) == 1
        assert "file.py" in result[0]


class TestGrep:
    """测试 grep 方法"""

    def test_grep_simple_pattern(self, fs, workspace):
        """测试简单模式搜索"""
        (workspace / "test.py").write_text("import os\nimport sys\nprint('hello')")

        result = fs.grep("import", glob="test.py", output_mode="files_with_matches")
        print(result)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_grep_with_type_filter(self, fs, workspace):
        """测试按文件类型过滤"""
        (workspace / "test.py").write_text("class Test:\n    pass")
        (workspace / "test.txt").write_text("class Test:\n    pass")

        result = fs.grep("class", workspace, type="py", output_mode="files_with_matches")
        assert any("test.py" in f for f in result)

    def test_grep_count_mode(self, fs, workspace):
        """测试计数模式"""
        (workspace / "test.py").write_text("import os\nimport sys")

        result = fs.grep("import", workspace, type="py", output_mode="count")
        assert isinstance(result, list)
        # 应该返回 "file:count" 格式

    def test_grep_content_mode(self, fs, workspace):
        """测试内容模式"""
        (workspace / "test.py").write_text("hello world\nhello python")

        result = fs.grep("hello", workspace, type="py", output_mode="content")
        assert isinstance(result, str)
        assert "hello" in result

    def test_grep_case_insensitive(self, fs, workspace):
        """测试忽略大小写"""
        (workspace / "test.py").write_text("HELLO world")

        result = fs.grep("hello", workspace, type="py", _i=True, output_mode="files_with_matches")
        assert len(result) >= 1

    def test_grep_dangerous_regex_blocked(self, fs, workspace):
        """测试危险正则表达式被阻止"""
        result = fs.grep("((a+)+)+", workspace, type="py")
        assert "Unsafe" in result or "Error" in result

    def test_grep_with_glob_pattern(self, fs, workspace):
        """测试带 glob 模式的搜索"""
        (workspace / "test.py").write_text("class Test")
        (workspace / "test.txt").write_text("class Test")

        result = fs.grep("class", workspace, glob="*.py", output_mode="files_with_matches")
        assert any("test.py" in f for f in result)


class TestSecurity:
    """测试安全功能"""

    def test_workspace_boundary_enforced(self, fs, workspace):
        """测试 workspace 边界强制执行"""
        # 尝试读取 workspace 外的文件
        result = fs.read("/etc/passwd")
        assert "Error" in result

    def test_symlink_blocked(self, fs, workspace):
        """测试符号链接被阻止"""
        # 尝试创建符号链接（如果系统支持）
        try:
            link = workspace / "link.txt"
            target = workspace / "target.txt"
            target.write_text("content")
            link.symlink_to(target)

            # glob 应该不包含符号链接
            result = fs.glob("*.txt")
            assert str(link) not in result
        except OSError:
            # 系统不支持符号链接，跳过测试
            pass

    def test_path_traversal_in_all_methods(self, fs):
        """测试所有方法都阻止路径遍历"""
        tests = [
            lambda: fs.read("../../../etc/passwd"),
            lambda: fs.write("../../../tmp/test.txt", "content"),
            lambda: fs.edit("../../../tmp/test.txt", "old", "new"),
            lambda: fs.glob("../../../tmp/*.txt"),
        ]

        for test in tests:
            result = test()
            if isinstance(result, str):
                assert "Error" in result or result == []
            if isinstance(result, list):
                assert result == []


class TestEdgeCases:
    """测试边缘情况"""

    def test_empty_file_read(self, fs, workspace):
        """测试读取空文件"""
        test_file = workspace / "empty.txt"
        test_file.write_text("")

        result = fs.read(str(test_file))
        assert result == "" or "1\t" in result

    def test_unicode_file_read(self, fs, workspace):
        """测试读取 Unicode 文件"""
        test_file = workspace / "unicode.txt"
        test_file.write_text("你好世界\n🚀 hello", encoding="utf-8")

        result = fs.read(str(test_file))
        assert "你好世界" in result

    def test_large_line_truncation(self, fs, workspace):
        """测试超长行被截断"""
        test_file = workspace / "long.txt"
        long_line = "x" * 20000
        test_file.write_text(long_line)

        result = fs.read(str(test_file))
        assert "truncated" in result

    def test_special_characters_in_edit(self, fs, workspace):
        """测试编辑特殊字符"""
        test_file = workspace / "special.txt"
        test_file.write_text("hello\n$world\n^test")

        result = fs.edit(str(test_file), "$world", "python")
        assert "$world" not in test_file.read_text()


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])
