import logging
from pathlib import Path

import pytest

from everlingo.setting import get_prompt_version
from everlingo.tools.user_doc import user_doc_get, user_doc_set


@pytest.fixture
def tmp_user_doc(monkeypatch, tmp_path):
    """把 USER_DOC_PATH 重定向到临时目录下的 USER.md。"""
    path = tmp_path / "USER.md"
    monkeypatch.setattr("everlingo.setting.USER_DOC_PATH", path)
    monkeypatch.setattr("everlingo.tools.user_doc.setting.USER_DOC_PATH", path)
    return path


def test_user_doc_get_returns_empty_when_missing(tmp_user_doc):
    """文件不存在时 user_doc_get 返回空串。"""
    assert user_doc_get.invoke({}) == ""


def test_user_doc_set_writes_content(tmp_user_doc):
    """user_doc_set 写入后 user_doc_get 应能读回相同内容。"""
    content = "# 我的偏好\n- 爱好：历史\n- 目标：雅思 7.0"
    user_doc_set.invoke({"content": content})
    assert user_doc_get.invoke({}) == content
    assert tmp_user_doc.read_text(encoding="utf-8") == content


def test_user_doc_set_creates_bak(tmp_user_doc):
    """user_doc_set 在旧文件存在时应把旧内容备份到 .md.bak。"""
    old = "旧内容"
    user_doc_set.invoke({"content": old})

    new = "新内容"
    user_doc_set.invoke({"content": new})

    bak_path = tmp_user_doc.with_suffix(".md.bak")
    assert bak_path.exists()
    assert bak_path.read_text(encoding="utf-8") == old
    assert tmp_user_doc.read_text(encoding="utf-8") == new


def test_user_doc_set_no_bak_when_missing(tmp_user_doc):
    """文件不存在时 user_doc_set 不应产生 .bak。"""
    user_doc_set.invoke({"content": "首次写入"})
    bak_path = tmp_user_doc.with_suffix(".md.bak")
    assert not bak_path.exists()


def test_user_doc_set_increments_prompt_version(tmp_user_doc):
    """user_doc_set 成功后 prompt 版本号应递增。"""
    version_before = get_prompt_version()
    user_doc_set.invoke({"content": "test"})
    version_after = get_prompt_version()
    assert version_after == version_before + 1


def test_user_doc_set_logs_tool_call(tmp_user_doc, caplog):
    """user_doc_set 调用应记录 debug 日志。"""
    caplog.set_level(logging.DEBUG, logger="everlingo")
    user_doc_set.invoke({"content": "logged content"})
    assert "tool_name: user_doc_set" in caplog.text
    assert "return:" in caplog.text


def test_user_doc_get_logs_tool_call(tmp_user_doc, caplog):
    """user_doc_get 调用应记录 debug 日志。"""
    caplog.set_level(logging.DEBUG, logger="everlingo")
    user_doc_get.invoke({})
    assert "tool_name: user_doc_get" in caplog.text
