#!/usr/bin/env python3
"""Tests for agent tools (file operations, shell, grep, etc.)."""

import os
import tempfile
import shutil
from llmproxy.tools import (
    _sanitize_path,
    read_file,
    write_file,
    list_directory,
    shell,
    grep,
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
    """Tests for read_file tool."""
    
    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
    
    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_read_existing_file(self):
        """Should read file contents."""
        with open("test.txt", "w") as f:
            f.write("line1\nline2\nline3\n")
        
        result = read_file("test.txt")
        assert "line1" in result
        assert "line2" in result
        assert "line3" in result
        print("✓ Read existing file works")
    
    def test_read_nonexistent_file(self):
        """Should return error for non-existent file."""
        result = read_file("nonexistent.txt")
        assert "Error" in result
        assert "not found" in result
        print("✓ Read non-existent file returns error")
    
    def test_read_directory(self):
        """Should return error when path is a directory."""
        os.makedirs("testdir")
        result = read_file("testdir")
        assert "Error" in result
        assert "is a directory" in result
        print("✓ Read directory returns error")
    
    def test_read_with_offset(self):
        """Should respect offset parameter."""
        with open("test.txt", "w") as f:
            for i in range(10):
                f.write(f"line{i+1}\n")
        
        result = read_file("test.txt", offset=5, limit=2)
        assert "line5" in result
        assert "line6" in result
        assert "line1" not in result
        assert "line10" not in result
        print("✓ Read with offset works")
    
    def test_read_with_limit(self):
        """Should respect limit parameter."""
        with open("test.txt", "w") as f:
            for i in range(100):
                f.write(f"line{i+1}\n")
        
        result = read_file("test.txt", offset=1, limit=10)
        lines = result.split("\n")
        # Header + 10 lines + empty line
        assert len([l for l in lines if l.startswith("line")]) == 10
        print("✓ Read with limit works")
    
    def test_read_empty_file(self):
        """Should handle empty files."""
        with open("empty.txt", "w") as f:
            f.write("")
        
        result = read_file("empty.txt")
        assert "lines 1-0 of 0" in result
        print("✓ Read empty file works")
    
    def test_read_binary_file(self):
        """Should handle binary files gracefully."""
        with open("binary.bin", "wb") as f:
            f.write(b"\x00\x01\x02\xff\xfe")
        
        result = read_file("binary.bin")
        assert "Error" not in result
        print("✓ Read binary file works")


class TestWriteFile:
    """Tests for write_file tool."""
    
    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
    
    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_write_new_file(self):
        """Should create and write to new file."""
        result = write_file("new.txt", "hello world")
        assert "Success" in result
        
        with open("new.txt", "r") as f:
            assert f.read() == "hello world"
        print("✓ Write new file works")
    
    def test_overwrite_existing(self):
        """Should overwrite existing file by default."""
        with open("existing.txt", "w") as f:
            f.write("old content")
        
        result = write_file("existing.txt", "new content")
        assert "Success" in result
        
        with open("existing.txt", "r") as f:
            assert f.read() == "new content"
        print("✓ Overwrite existing works")
    
    def test_append_mode(self):
        """Should append when mode=append."""
        with open("append.txt", "w") as f:
            f.write("first ")
        
        result = write_file("append.txt", "second", mode="append")
        assert "Success" in result
        
        with open("append.txt", "r") as f:
            assert f.read() == "first second"
        print("✓ Append mode works")
    
    def test_create_parent_dirs(self):
        """Should create parent directories."""
        result = write_file("deep/nested/path/file.txt", "content")
        assert "Success" in result
        assert os.path.exists("deep/nested/path/file.txt")
        print("✓ Create parent directories works")
    
    def test_path_traversal_blocked(self):
        """Should block path traversal in write."""
        result = write_file("../../../etc/passwd", "evil")
        assert "Error" in result
        print("✓ Path traversal blocked in write")


class TestListDirectory:
    """Tests for list_directory tool."""
    
    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
    
    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_list_current_directory(self):
        """Should list current directory."""
        with open("file1.txt", "w") as f:
            f.write("content")
        with open("file2.txt", "w") as f:
            f.write("content")
        os.makedirs("subdir")
        
        result = list_directory(".")
        assert "file1.txt" in result
        assert "file2.txt" in result
        assert "subdir" in result
        assert "[file" in result
        assert "[dir" in result
        print("✓ List current directory works")
    
    def test_list_nested_directory(self):
        """Should list nested directory."""
        os.makedirs("nested/dir")
        with open("nested/dir/file.txt", "w") as f:
            f.write("content")
        
        result = list_directory("nested/dir")
        assert "file.txt" in result
        print("✓ List nested directory works")
    
    def test_list_nonexistent_directory(self):
        """Should return error for non-existent directory."""
        result = list_directory("nonexistent")
        assert "Error" in result
        print("✓ List non-existent directory returns error")
    
    def test_list_file_as_directory(self):
        """Should return error when path is a file."""
        with open("file.txt", "w") as f:
            f.write("content")
        
        result = list_directory("file.txt")
        assert "Error" in result
        assert "is not a directory" in result
        print("✓ List file as directory returns error")


class TestShell:
    """Tests for shell tool."""
    
    def test_echo_command(self):
        """Should execute echo command."""
        result = shell("echo hello")
        assert "STDOUT:" in result
        assert "hello" in result
        assert "Exit code: 0" in result
        print("✓ Echo command works")
    
    def test_stderr_output(self):
        """Should capture stderr."""
        result = shell("echo error >&2")
        assert "STDERR:" in result
        assert "error" in result
        print("✓ Stderr capture works")
    
    def test_nonzero_exit_code(self):
        """Should report non-zero exit codes."""
        result = shell("exit 1")
        assert "Exit code: 1" in result
        print("✓ Non-zero exit code reported")
    
    def test_timeout(self):
        """Should timeout long-running commands."""
        result = shell("sleep 10", timeout=1)
        assert "timed out" in result
        print("✓ Timeout works")
    
    def test_empty_output(self):
        """Should handle commands with no output."""
        result = shell("true")
        assert "no output" in result or "Exit code: 0" in result
        print("✓ Empty output handled")


class TestGrep:
    """Tests for grep tool."""
    
    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        os.chdir(self.test_dir)
    
    def teardown_method(self):
        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)
    
    def test_grep_single_file(self):
        """Should search in a single file."""
        with open("test.txt", "w") as f:
            f.write("hello world\nfoo bar\nhello again\n")
        
        result = grep("hello", "test.txt")
        assert "test.txt:1:" in result
        assert "test.txt:3:" in result
        assert "foo bar" not in result
        print("✓ Grep single file works")
    
    def test_grep_directory(self):
        """Should search recursively in directory."""
        with open("file1.txt", "w") as f:
            f.write("target line\n")
        with open("file2.txt", "w") as f:
            f.write("other content\n")
        
        result = grep("target")
        assert "file1.txt" in result
        assert "target line" in result
        assert "file2.txt" not in result
        print("✓ Grep directory works")
    
    def test_grep_no_matches(self):
        """Should report when no matches found."""
        with open("test.txt", "w") as f:
            f.write("hello world\n")
        
        result = grep("nonexistent", "test.txt")
        assert "No matches" in result
        print("✓ Grep no matches works")
    
    def test_grep_with_glob(self):
        """Should filter by glob pattern."""
        with open("file.txt", "w") as f:
            f.write("target\n")
        with open("file.py", "w") as f:
            f.write("target\n")
        
        result = grep("target", ".", glob="*.py")
        assert "file.py" in result
        assert "file.txt" not in result
        print("✓ Grep with glob works")
    
    def test_grep_limit_matches(self):
        """Should limit to 100 matches."""
        with open("many.txt", "w") as f:
            for i in range(150):
                f.write(f"target line {i}\n")
        
        result = grep("target", "many.txt")
        lines = result.split("\n")
        assert len(lines) <= 100
        print("✓ Grep limit matches works")
    
    def test_grep_limit_files(self):
        """Should limit to 50 files."""
        for i in range(60):
            with open(f"file{i}.txt", "w") as f:
                f.write("target\n")
        
        result = grep("target")
        # Should complete without error
        assert "target" in result or "No matches" in result
        print("✓ Grep limit files works")


def run_all_tests():
    """Run all tool tests."""
    print("\n=== Testing Path Sanitization ===")
    t = TestSanitizePath()
    for name in dir(t):
        if name.startswith("test_"):
            t.setup_method()
            getattr(t, name)()
            t.teardown_method()
    
    print("\n=== Testing Read File ===")
    t = TestReadFile()
    for name in dir(t):
        if name.startswith("test_"):
            t.setup_method()
            getattr(t, name)()
            t.teardown_method()
    
    print("\n=== Testing Write File ===")
    t = TestWriteFile()
    for name in dir(t):
        if name.startswith("test_"):
            t.setup_method()
            getattr(t, name)()
            t.teardown_method()
    
    print("\n=== Testing List Directory ===")
    t = TestListDirectory()
    for name in dir(t):
        if name.startswith("test_"):
            t.setup_method()
            getattr(t, name)()
            t.teardown_method()
    
    print("\n=== Testing Shell ===")
    t = TestShell()
    for name in dir(t):
        if name.startswith("test_"):
            getattr(t, name)()
    
    print("\n=== Testing Grep ===")
    t = TestGrep()
    for name in dir(t):
        if name.startswith("test_"):
            t.setup_method()
            getattr(t, name)()
            t.teardown_method()


if __name__ == "__main__":
    run_all_tests()
    print("\n✅ All tool tests passed!")
