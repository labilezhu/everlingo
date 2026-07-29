"""多用户支持 — PR0 骨架测试

验证子命令派发不爆栈，`--help` 退出码 0。
"""

from __future__ import annotations

import subprocess
import sys


def _everlingo_cli(*args: str) -> subprocess.CompletedProcess:
    """Run `everlingo <args>` and return CompletedProcess."""
    return subprocess.run(
        [sys.executable, "-m", "everlingo", *args],
        capture_output=True,
        text=True,
    )


class TestMainHelp:
    def test_main_help_lists_ws_router(self):
        """everlingo --help 列出 ws_router 子命令"""
        result = _everlingo_cli("--help")
        assert result.returncode == 0
        assert "ws_router" in result.stdout
        assert "前台反代" in result.stdout

    def test_main_help_lists_ws_master(self):
        """everlingo --help 列出 ws_master 子命令"""
        result = _everlingo_cli("--help")
        assert result.returncode == 0
        assert "ws_master" in result.stdout
        assert "后台编排" in result.stdout


class TestWsRouterSubcommand:
    def test_ws_router_help_exits_zero(self):
        """everlingo ws_router --help 退出码 0"""
        result = _everlingo_cli("ws_router", "--help")
        assert result.returncode == 0

    def test_ws_router_help_contains_ws_router(self):
        """everlingo ws_router --help 输出包含 ws_router"""
        result = _everlingo_cli("ws_router", "--help")
        assert "ws_router" in result.stdout

    def test_ws_router_help_has_usage(self):
        """everlingo ws_router --help 输出包含 usage"""
        result = _everlingo_cli("ws_router", "--help")
        assert "usage:" in result.stdout.lower()


class TestWsMasterSubcommand:
    def test_ws_master_help_exits_zero(self):
        """everlingo ws_master --help 退出码 0"""
        result = _everlingo_cli("ws_master", "--help")
        assert result.returncode == 0

    def test_ws_master_help_contains_ws_master(self):
        """everlingo ws_master --help 输出包含 ws_master"""
        result = _everlingo_cli("ws_master", "--help")
        assert "ws_master" in result.stdout

    def test_ws_master_help_has_usage(self):
        """everlingo ws_master --help 输出包含 usage"""
        result = _everlingo_cli("ws_master", "--help")
        assert "usage:" in result.stdout.lower()


class TestPackageImport:
    def test_ws_router_importable(self):
        """ws_router 包可 import"""
        import everlingo.ws_router  # noqa: F811

    def test_ws_master_importable(self):
        """ws_master 包可 import"""
        import everlingo.ws_master  # noqa: F811