# ref: docs/impl-spec/worksplace/vault-version-control.md §4.2 — ssh 远端凭证
#   * auth.ssh_private_key_file 非空 → 复制/软链到临时文件（避免拖慢且不留长驻），
#     构造 GIT_SSH_COMMAND 注入 git；
#   * 为空 → 走系统 ~/.ssh/，但仍注入 -o StrictHostKeyChecking=accept-new
#     （§11.3：非交互 subprocess 首次连接 host key 验证）。
# https_pat 模式由 committer 层用 git 的 http.extraheader 配置注入（见 git.push）。

from __future__ import annotations

import base64
import logging
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# 首次连接自动接受 host key（写入 known_hosts），后续严格校验
_SSH_OPTIONS = "-o StrictHostKeyChecking=accept-new -o IdentitiesOnly=yes"
_GIT_SSH_TEMPLATE = "ssh {options}"


@dataclass
class SSHCommandContext:
    """一次 git 远端操作期间 ssh / PAT 凭证的封装。

    - start()/close() 管理临时私钥文件生命周期；
    - env() 返回需要注入 git 的环境变量（ssh 模式）；
    - extraheader() 返回 https_pat 模式所需的 git config。
    """

    private_key_file: str = ""
    method: str = "ssh"
    pat: str = ""
    _tmp_key: Path | None = field(default=None, init=False, repr=False)

    def configure(self, *, method: str, ssh_private_key_file: str = "", pat: str = "") -> None:
        self.method = method
        self.pat = pat
        self.private_key_file = ssh_private_key_file
        self.close()

    def start(self) -> None:
        """按需创建临时私钥。仅 ssh 且显式指定私钥时才有临时文件。"""
        if self.method != "ssh" or not self.private_key_file:
            return
        src = Path(self.private_key_file).expanduser()
        if not src.is_file():
            raise FileNotFoundError(f"ssh 私钥不存在: {src}")
        fd, raw_path = tempfile.mkstemp(prefix="everlingo-sshkey-", suffix=".pem")
        import os

        os.close(fd)
        self._tmp_key = Path(raw_path)
        try:
            os.chmod(raw_path, 0o600)
            shutil.copy2(src, raw_path)
            logger.debug("ssh 私钥复制到临时文件 %s", raw_path)
        except Exception:
            self._tmp_key.unlink(missing_ok=True)
            self._tmp_key = None
            raise

    def close(self) -> None:
        if self._tmp_key is not None:
            try:
                self._tmp_key.unlink(missing_ok=True)
            except OSError:
                pass
            self._tmp_key = None

    def env(self) -> dict[str, str]:
        """ssh 模式返回 GIT_SSH_COMMAND；https 模式返回空。"""
        if self.method != "ssh":
            return {}
        if self._tmp_key is not None:
            cmd = f"ssh -i {self._tmp_key} {_SSH_OPTIONS}"
        else:
            cmd = f"ssh {_SSH_OPTIONS}"
        return {"GIT_SSH_COMMAND": cmd}

    def extraheader(self) -> dict[str, str] | None:
        """https_pat 模式返回 http.extraheader git config（Basic auth）。"""
        if self.method != "https_pat" or not self.pat:
            return None
        user = "x-access-token"  # GitHub PAT 作为密码的用户名占位
        token = base64.b64encode(f"{user}:{self.pat}".encode()).decode()
        return {"http.extraheader": f"Authorization: Basic {token}"}