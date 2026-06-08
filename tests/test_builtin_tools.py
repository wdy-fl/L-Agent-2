"""Tests for step-7: built-in tools."""

from agent.tools.builtin import (
    AUTO_APPROVE_TOOLS,
    ALWAYS_CONFIRM_TOOLS,
)
from agent.tools.builtin.file_ops import (
    _read_file_handler,
    _write_file_handler,
    _list_directory_handler,
    _search_file_handler,
)
from agent.tools.builtin.terminal import _terminal_handler
from agent.tools.builtin.web import _web_fetch_handler


class TestReadFile:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "hello.txt"
        f.write_text("line1\nline2\nline3\n")
        result = _read_file_handler(str(f))
        assert "1\tline1" in result
        assert "3\tline3" in result

    def test_read_with_offset_limit(self, tmp_path):
        f = tmp_path / "data.txt"
        f.write_text("\n".join(f"line{i}" for i in range(1, 11)))
        result = _read_file_handler(str(f), offset=3, limit=2)
        assert "3\tline3" in result
        assert "4\tline4" in result
        assert "5\t" not in result

    def test_read_nonexistent(self):
        try:
            _read_file_handler("/nonexistent/path.txt")
            assert False, "Should raise"
        except FileNotFoundError:
            pass

    def test_read_directory_raises(self, tmp_path):
        try:
            _read_file_handler(str(tmp_path))
            assert False, "Should raise"
        except ValueError:
            pass


class TestWriteFile:
    def test_write_creates_file(self, tmp_path):
        target = tmp_path / "out.txt"
        result = _write_file_handler(str(target), "hello world")
        assert target.read_text() == "hello world"
        assert "11 bytes" in result

    def test_write_creates_parent_dirs(self, tmp_path):
        target = tmp_path / "a" / "b" / "c.txt"
        _write_file_handler(str(target), "nested")
        assert target.read_text() == "nested"

    def test_write_overwrites(self, tmp_path):
        target = tmp_path / "x.txt"
        target.write_text("old")
        _write_file_handler(str(target), "new")
        assert target.read_text() == "new"


class TestListDirectory:
    def test_list_flat(self, tmp_path):
        (tmp_path / "a.py").touch()
        (tmp_path / "b.txt").touch()
        (tmp_path / "sub").mkdir()
        result = _list_directory_handler(str(tmp_path))
        assert "a.py" in result
        assert "sub/" in result

    def test_list_with_pattern(self, tmp_path):
        (tmp_path / "a.py").touch()
        (tmp_path / "b.txt").touch()
        result = _list_directory_handler(str(tmp_path), pattern="*.py")
        assert "a.py" in result
        assert "b.txt" not in result

    def test_list_recursive(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "deep.py").touch()
        result = _list_directory_handler(str(tmp_path), recursive=True)
        assert "deep.py" in result

    def test_list_nonexistent(self):
        try:
            _list_directory_handler("/nonexistent")
            assert False
        except FileNotFoundError:
            pass


class TestSearchFile:
    def test_search_finds_match(self, tmp_path):
        f = tmp_path / "code.py"
        f.write_text("def hello():\n    pass\ndef world():\n    pass\n")
        result = _search_file_handler("hello", str(tmp_path))
        assert "code.py:1:" in result
        assert "def hello" in result

    def test_search_with_file_pattern(self, tmp_path):
        (tmp_path / "a.py").write_text("target\n")
        (tmp_path / "b.txt").write_text("target\n")
        result = _search_file_handler("target", str(tmp_path), file_pattern="*.py")
        assert "a.py" in result
        assert "b.txt" not in result

    def test_search_no_match(self, tmp_path):
        (tmp_path / "f.txt").write_text("nothing here\n")
        result = _search_file_handler("xyz123", str(tmp_path))
        assert "No matches" in result

    def test_search_invalid_regex(self, tmp_path):
        try:
            _search_file_handler("[invalid", str(tmp_path))
            assert False
        except ValueError:
            pass


class TestTerminal:
    def test_simple_command(self):
        result = _terminal_handler("echo hello")
        assert "hello" in result
        assert "exit_code: 0" in result

    def test_stderr_captured(self):
        result = _terminal_handler("echo err >&2")
        assert "[stderr]" in result
        assert "err" in result

    def test_nonzero_exit(self):
        result = _terminal_handler("exit 1")
        assert "exit_code: 1" in result

    def test_timeout(self):
        try:
            _terminal_handler("sleep 10", timeout=1)
            assert False
        except TimeoutError:
            pass

    def test_cwd(self, tmp_path):
        result = _terminal_handler("pwd", cwd=str(tmp_path))
        assert str(tmp_path) in result


class TestWebFetch:
    def test_fetch_invalid_url(self):
        try:
            _web_fetch_handler("http://this-domain-does-not-exist-xyz.invalid")
            assert False
        except ConnectionError:
            pass


class TestApprovalConfig:
    def test_auto_approve_set(self):
        assert "read_file" in AUTO_APPROVE_TOOLS
        assert "list_directory" in AUTO_APPROVE_TOOLS
        assert "search_file" in AUTO_APPROVE_TOOLS
        assert "think" in AUTO_APPROVE_TOOLS

    def test_always_confirm_set(self):
        assert "terminal" in ALWAYS_CONFIRM_TOOLS
        assert "write_file" in ALWAYS_CONFIRM_TOOLS

    def test_no_overlap(self):
        assert AUTO_APPROVE_TOOLS & ALWAYS_CONFIRM_TOOLS == set()
