# ref: docs/impl-spec/worksplace/vault-version-control.md §4.2 — ssh_key 测试

from __future__ import annotations

from pathlib import Path

from everlingo.mem.vault.version.ssh_key import SSHCommandContext


def test_default_no_env_no_tmp(tmp_path: Path):
    """method 非 ssh 时不产生临时文件、不注入 GIT_SSH_COMMAND。"""
    ctx = SSHCommandContext()
    ctx.configure(method="https_none")
    ctx.start()
    assert ctx.env() == {}
    assert ctx.extraheader() is None
    assert ctx._tmp_key is None
    ctx.close()


def test_ssh_system_key_injects_env(tmp_path: Path):
    """ssh + 空私钥路径：不复制临时文件，但注入 accept-new 选项。"""
    ctx = SSHCommandContext()
    ctx.configure(method="ssh", ssh_private_key_file="")
    ctx.start()
    env = ctx.env()
    assert "GIT_SSH_COMMAND" in env
    assert env["GIT_SSH_COMMAND"].startswith("ssh ")
    assert "-o StrictHostKeyChecking=accept-new" in env["GIT_SSH_COMMAND"]
    assert ctx._tmp_key is None
    ctx.close()


def test_ssh_private_key_copies_to_tmp(tmp_path: Path):
    key = tmp_path / "id_rsa"
    key.write_text("fake-private-key", encoding="utf-8")
    ctx = SSHCommandContext()
    ctx.configure(method="ssh", ssh_private_key_file=str(key))
    ctx.start()
    assert ctx._tmp_key is not None
    assert ctx._tmp_key.exists()
    assert ctx._tmp_key.read_text(encoding="utf-8") == "fake-private-key"
    env = ctx.env()
    assert f"-i {ctx._tmp_key}" in env["GIT_SSH_COMMAND"]
    assert "IdentitiesOnly=yes" in env["GIT_SSH_COMMAND"]
    tmp = ctx._tmp_key
    ctx.close()
    assert not tmp.exists()


def test_ssh_missing_private_key_raises(tmp_path: Path):
    ctx = SSHCommandContext()
    ctx.configure(method="ssh", ssh_private_key_file=str(tmp_path / "nope"))
    try:
        ctx.start()
        assert False, "应抛 FileNotFoundError"
    except FileNotFoundError:
        pass
    finally:
        ctx.close()


def test_https_pat_basic_auth():
    ctx = SSHCommandContext()
    ctx.configure(method="https_pat", pat="github_pat_secret")
    ctx.start()
    extra = ctx.extraheader()
    assert extra is not None
    assert "http.extraheader" in extra
    assert "Authorization: Basic" in extra["http.extraheader"]
    import base64

    decoded = base64.b64decode(
        extra["http.extraheader"].split("Basic ")[1]
    ).decode()
    assert decoded == "x-access-token:github_pat_secret"
    # https 模式不注入 GIT_SSH_COMMAND
    assert ctx.env() == {}
    ctx.close()


def test_configure_resets_tmp(tmp_path: Path):
    key = tmp_path / "id_ed25519"
    key.write_text("k", encoding="utf-8")
    ctx = SSHCommandContext()
    ctx.configure(method="ssh", ssh_private_key_file=str(key))
    ctx.start()
    first = ctx._tmp_key
    ctx.configure(method="https_none")  # 重配应清理旧临时文件
    assert first is None or not first.exists()
    assert ctx._tmp_key is None
    ctx.close()