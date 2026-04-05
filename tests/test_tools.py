#!/usr/bin/env python3
"""Tests for agent tools (file operations, shell, grep, etc.)."""

import asyncio
import os
import shutil
import tempfile

import pytest

from llmproxy.tools import (
    ASYNC_TOOLS,
    _sanitize_path,
    execute_tool,
    grep,
    list_directory,
    read_file,
    shell,
    write_file,
)


class TestSanitizePath:
    """Tests for path sanitization and traversal protection."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_normal_path(self):
        """Normal paths should work."""
        result = _sanitize_path("test.txt")
        assert result == os.path.join(self.test_dir, "test.txt")
        print("✓ Normal path accepted")

    def test_path_traversal_blocked(self):
        """Path traversal attacks should be blocked."""
        try:
            _sanitize_path("../../../etc/passwd")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "outside the allowed workspace" in str(e)
        print("✓ Path traversal blocked")

    def test_symlink_bypass_blocked(self):
        """Symlink bypass attempts should be blocked."""
        # Create a symlink pointing outside the test directory
        os.symlink("/etc", "link_to_etc")
        try:
            _sanitize_path("link_to_etc/passwd")
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "outside the allowed workspace" in str(e)
        print("✓ Symlink bypass blocked")

    def test_nested_path(self):
        """Nested paths within workspace should work."""
        os.makedirs("subdir/nested")
        result = _sanitize_path("subdir/nested/file.txt")
        expected = os.path.join(self.test_dir, "subdir", "nested", "file.txt")
        assert result == expected
        print("✓ Nested path works")

    def test_absolute_path_blocked(self):
        """Absolute paths outside workspace should be blocked."""
        try:
            _sanitize_path("/etc/passwd")
            assert False, "Should have raised ValueError"
        except ValueError:
            pass
        print("✓ Absolute path outside workspace blocked")


class TestReadFile:
    """Tests for read_file tool (async)."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_read_existing_file(self):
        """Should read file contents."""
        with open("test.txt", "w") as f:
            f.write("line1\nline2\nline3\n")

        result = await read_file("test.txt")
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result
        print("✓ Read existing file works")

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self):
        """Should return error for non-existent file."""
        result = await read_file("nonexistent.txt")
        assert "Error" in result
        assert "not found" in result
        print("✓ Nonexistent file error works")

    @pytest.mark.asyncio
    async def test_read_directory(self):
        """Should return error when trying to read directory."""
        os.makedirs("testdir")
        result = await read_file("testdir")
        assert "Error" in result
        assert "is a directory" in result
        print("✓ Directory read error works")

    @pytest.mark.asyncio
    async def test_read_with_offset(self):
        """Should respect offset parameter."""
        with open("test.txt", "w") as f:
            for i in range(1, 11):
                f.write(f"line{i}\n")

        result = await read_file("test.txt", offset=5, limit=3)
        assert "line5" in result
        assert "line6" in result
        assert "line7" in result
        assert "line1" not in result  # Before offset
        assert "line8" not in result  # After limit
        print("✓ Offset parameter works")

    @pytest.mark.asyncio
    async def test_read_with_limit(self):
        """Should respect limit parameter."""
        with open("test.txt", "w") as f:
            for i in range(1, 21):
                f.write(f"line{i}\n")

        result = await read_file("test.txt", limit=5)
        # Should only show lines 1-5
        assert result.count("line") == 6  # 5 in content + 1 in header "lines"
        print("✓ Limit parameter works")

    @pytest.mark.asyncio
    async def test_read_empty_file(self):
        """Should handle empty files."""
        with open("empty.txt", "w"):
            pass

        result = await read_file("empty.txt")
        assert "lines 1-0" in result  # Header shows 0 lines
        print("✓ Empty file handled")

    @pytest.mark.asyncio
    async def test_read_binary_file(self):
        """Should handle binary files with errors="ignore"."""
        with open("binary.bin", "wb") as f:
            f.write(b"\x00\x01\x02\x03\xff\xfe")

        result = await read_file("binary.bin")
        assert "Error" not in result  # Should not error
        print("✓ Binary file handled")


class TestWriteFile:
    """Tests for write_file tool (async)."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_write_new_file(self):
        """Should create new file."""
        result = await write_file("new.txt", "Hello World")
        assert "Success" in result

        with open("new.txt") as f:
            content = f.read()
        assert content == "Hello World"
        print("✓ Write new file works")

    @pytest.mark.asyncio
    async def test_overwrite_existing(self):
        """Should overwrite existing file."""
        with open("existing.txt", "w") as f:
            f.write("old content")

        result = await write_file("existing.txt", "new content")
        assert "Success" in result

        with open("existing.txt") as f:
            content = f.read()
        assert content == "new content"
        print("✓ Overwrite works")

    @pytest.mark.asyncio
    async def test_append_mode(self):
        """Should append to file in append mode."""
        with open("append.txt", "w") as f:
            f.write("first")

        result = await write_file("append.txt", "second", mode="append")
        assert "Success" in result

        with open("append.txt") as f:
            content = f.read()
        assert content == "firstsecond"
        print("✓ Append mode works")

    @pytest.mark.asyncio
    async def test_create_parent_dirs(self):
        """Should create parent directories if needed."""
        result = await write_file("deep/nested/path/file.txt", "content")
        assert "Success" in result
        assert os.path.exists("deep/nested/path/file.txt")
        print("✓ Parent directory creation works")

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self):
        """Should block path traversal in write."""
        result = await write_file("../../../etc/passwd", "hacked")
        assert "Error" in result
        assert "outside" in result.lower() or "traversal" in result.lower()
        print("✓ Path traversal blocked in write")


class TestListDirectory:
    """Tests for list_directory tool (sync)."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_list_current_directory(self):
        """Should list current directory contents."""
        # Create some files and directories
        with open("file1.txt", "w") as f:
            f.write("content")
        with open("file2.py", "w") as f:
            f.write("python")
        os.makedirs("subdir")

        result = list_directory(".")
        assert "file1.txt" in result
        assert "file2.py" in result
        assert "subdir" in result
        assert "[file]" in result
        assert "[dir ]" in result
        print("✓ List current directory works")

    def test_list_nested_directory(self):
        """Should list nested directory."""
        os.makedirs("level1/level2")
        with open("level1/level2/deep.txt", "w") as f:
            f.write("deep")

        result = list_directory("level1/level2")
        assert "deep.txt" in result
        print("✓ List nested directory works")

    def test_list_nonexistent_directory(self):
        """Should return error for non-existent directory."""
        result = list_directory("nonexistent")
        assert "Error" in result
        print("✓ Nonexistent directory error works")

    def test_list_file_as_directory(self):
        """Should return error when path is a file."""
        with open("notadir.txt", "w") as f:
            f.write("content")

        result = list_directory("notadir.txt")
        assert "Error" in result
        assert "is not a directory" in result
        print("✓ File as directory error works")


class TestShell:
    """Tests for shell tool (sync)."""

    def test_echo_command(self):
        """Should execute echo command."""
        result = shell("echo 'Hello World'")
        assert "Hello World" in result
        assert "Exit code: 0" in result
        print("✓ Echo command works")

    def test_stderr_output(self):
        """Should capture stderr."""
        result = shell("echo 'error' >&2")
        assert "STDERR" in result
        assert "error" in result
        print("✓ Stderr capture works")

    def test_nonzero_exit_code(self):
        """Should report non-zero exit codes."""
        result = shell("exit 1")
        assert "Exit code: 1" in result
        print("✓ Non-zero exit code works")

    def test_timeout(self):
        """Should timeout long-running commands."""
        result = shell("sleep 10", timeout=1)
        assert "Error" in result
        assert "timed out" in result.lower()
        print("✓ Timeout works")

    def test_empty_output(self):
        """Should handle commands with no output."""
        result = shell("true")
        assert "Exit code: 0" in result
        print("✓ Empty output handled")


class TestGrep:
    """Tests for grep tool (async)."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_grep_single_file(self):
        """Should search single file."""
        with open("test.txt", "w") as f:
            f.write("hello world\nfoo bar\nhello again\n")

        result = await grep("hello", "test.txt")
        assert "hello world" in result
        assert "hello again" in result
        assert "foo bar" not in result  # Doesn't match
        print("✓ Grep single file works")

    @pytest.mark.asyncio
    async def test_grep_directory(self):
        """Should search directory recursively."""
        with open("file1.txt", "w") as f:
            f.write("match here\n")
        with open("file2.txt", "w") as f:
            f.write("different text\n")
        os.makedirs("subdir")
        with open("subdir/file3.txt", "w") as f:
            f.write("match in subdir\n")

        result = await grep("match", ".")
        assert "match here" in result
        assert "match in subdir" in result
        assert "different text" not in result
        print("✓ Grep directory works")

    @pytest.mark.asyncio
    async def test_grep_no_matches(self):
        """Should report no matches."""
        with open("test.txt", "w") as f:
            f.write("content\n")

        result = await grep("nonexistent", "test.txt")
        assert "No matches" in result
        print("✓ No matches reported")

    @pytest.mark.asyncio
    async def test_grep_with_glob(self):
        """Should filter by glob pattern."""
        with open("script.py", "w") as f:
            f.write("def hello(): pass\n")
        with open("readme.txt", "w") as f:
            f.write("hello world\n")

        result = await grep("hello", ".", glob="*.py")
        assert "script.py" in result
        assert "readme.txt" not in result  # Filtered by glob
        print("✓ Grep with glob works")

    @pytest.mark.asyncio
    async def test_grep_limit_results(self):
        """Should limit to 100 results."""
        with open("many.txt", "w") as f:
            for i in range(150):
                f.write(f"match line {i}\n")

        result = await grep("match", "many.txt")
        # Should be limited to 100 results
        assert result.count("match") == 100
        print("✓ Grep result limit works")


class TestExecuteTool:
    """Tests for execute_tool function with async support."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_execute_async_tool(self):
        """Should execute async tool (read_file)."""
        with open("test.txt", "w") as f:
            f.write("hello")

        result = await execute_tool("read_file", {"path": "test.txt"})
        assert "hello" in result
        print("✓ Execute async tool works")

    @pytest.mark.asyncio
    async def test_execute_sync_tool(self):
        """Should execute sync tool (list_directory)."""
        with open("file.txt", "w") as f:
            f.write("content")

        result = await execute_tool("list_directory", {"path": "."})
        assert "file.txt" in result
        print("✓ Execute sync tool works")

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Should handle unknown tool."""
        result = await execute_tool("unknown_tool", {})
        assert "Error" in result
        assert "unknown" in result.lower()
        print("✓ Unknown tool error works")

    @pytest.mark.asyncio
    async def test_async_tools_set(self):
        """Should have correct async tools registered."""
        expected_async = {"read_file", "write_file", "grep", "search_web", "fetch_url", "http_request"}
        assert expected_async == ASYNC_TOOLS
        print("✓ Async tools set correct")


# Backward compatibility: synchronous wrappers for direct use
def test_sync_wrapper_read_file():
    """Test that read_file can be called via asyncio.run for sync contexts."""
    test_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()
    os.chdir(test_dir)
    try:
        with open("test.txt", "w") as f:
            f.write("async content")

        result = asyncio.run(read_file("test.txt"))
        assert "async content" in result
        print("✓ Sync wrapper for read_file works")
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(test_dir, ignore_errors=True)
