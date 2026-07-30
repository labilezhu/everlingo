"""WS-Master CLI 子命令。

直连 sqlite，不走 daemon。支持：
  user add/list/rm
  pat add/list/rm
  ws add/list/rm/start/stop/set-default
  identity list/unlink
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from pathlib import Path

from .config import MasterConfig, host_to_container_ws_path
from .db import get_conn
from .pat_utils import generate_pat
from .repo import IdentityRepo, PatRepo, UserRepo, WsContainerRepo


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="everlingo ws_master",
        description="WS-Master 运维 CLI（直连 sqlite，不走 daemon）",
    )
    sub = parser.add_subparsers(dest="ws_master_cmd", required=True)

    # ---- user ----
    p_user = sub.add_parser("user", help="用户管理")
    user_sub = p_user.add_subparsers(dest="user_cmd", required=True)

    p_user_add = user_sub.add_parser("add", help="创建用户")
    p_user_add.add_argument("--name", required=True, help="用户名（英文字母 + 下划线）")
    p_user_add.add_argument("--display-name", required=True, help="展示名")
    p_user_add.add_argument("--password", default=None, help="密码（指定则跳过确认，不指定则交互输入）")

    p_user_list = user_sub.add_parser("list", help="列出所有用户")

    p_user_rm = user_sub.add_parser("rm", help="删除用户")
    p_user_rm.add_argument("--name", required=True, help="用户名")
    p_user_rm.add_argument("--purge", action="store_true", help="同时 stop+remove 所有 ws-container 并删 host 目录")

    # ---- pat ----
    p_pat = sub.add_parser("pat", help="PAT 管理")
    pat_sub = p_pat.add_subparsers(dest="pat_cmd", required=True)

    p_pat_add = pat_sub.add_parser("add", help="生成 PAT")
    p_pat_add.add_argument("--user", required=True, help="用户名")
    p_pat_add.add_argument("--label", required=True, help="标签")
    p_pat_add.add_argument("--expires", default=None, help="过期时间（ISO8601 或相对天数如 365d）")

    p_pat_list = pat_sub.add_parser("list", help="列出 PAT")
    p_pat_list.add_argument("--user", required=True, help="用户名")

    p_pat_rm = pat_sub.add_parser("rm", help="吊销 PAT")
    p_pat_rm.add_argument("--id", required=True, dest="pat_id", help="PAT ID")

    # ---- ws ----
    p_ws = sub.add_parser("ws", help="ws-container 管理")
    ws_sub = p_ws.add_subparsers(dest="ws_cmd", required=True)

    p_ws_add = ws_sub.add_parser("add", help="新增 ws-container")
    p_ws_add.add_argument("--user", required=True, help="用户名")

    p_ws_list = ws_sub.add_parser("list", help="列出 ws-container")
    p_ws_list.add_argument("--user", default=None, help="按用户名筛选")

    p_ws_rm = ws_sub.add_parser("rm", help="删除 ws-container")
    p_ws_rm.add_argument("--id", required=True, dest="ws_id", help="ws-container ID")
    p_ws_rm.add_argument("--purge", action="store_true", help="同时 stop+remove 容器并删 host 目录")

    p_ws_start = ws_sub.add_parser("start", help="强制拉起 ws-container")
    p_ws_start.add_argument("--id", required=True, dest="ws_id", help="ws-container ID")

    p_ws_stop = ws_sub.add_parser("stop", help="强制停机 ws-container")
    p_ws_stop.add_argument("--id", required=True, dest="ws_id", help="ws-container ID")

    p_ws_set_default = ws_sub.add_parser("set-default", help="切换默认 ws-container")
    p_ws_set_default.add_argument("--id", required=True, dest="ws_id", help="ws-container ID")

    # ---- identity ----
    p_identity = sub.add_parser("identity", help="外部身份管理")
    identity_sub = p_identity.add_subparsers(dest="identity_cmd", required=True)

    p_identity_list = identity_sub.add_parser("list", help="列出外部身份")
    p_identity_list.add_argument("--user", required=True, help="用户名")

    p_identity_unlink = identity_sub.add_parser("unlink", help="解绑外部身份")
    p_identity_unlink.add_argument("--id", required=True, dest="identity_id", help="identity ID")

    return parser


def _load_config_and_db(args: argparse.Namespace) -> tuple:
    """Load config and connect to DB.

    Uses --config if provided, otherwise searches for ws_master.yaml in cwd or ~/.everlingo/.
    """
    config_path = getattr(args, "config", None)
    if config_path:
        config = MasterConfig.load(config_path)
    else:
        # Try default locations
        candidates = [
            Path.cwd() / "ws_master.yaml",
            Path.home() / ".everlingo" / "ws_master.yaml",
        ]
        for c in candidates:
            if c.exists():
                config = MasterConfig.load(c)
                break
        else:
            print("Error: no ws_master.yaml found. Use --config to specify path.", file=sys.stderr)
            sys.exit(1)
    conn = get_conn(config.db)
    return config, conn


def _hash_password(password: str) -> str:
    """Hash a password using PBKDF2-SHA256.

    Uses stdlib only (no bcrypt dependency). The hash is stored in
    password_hash field and used for authentication.
    """
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600000)
    return f"$pbkdf2-sha256$600000${salt.hex()}${dk.hex()}"


def _check_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored PBKDF2 hash."""
    parts = stored_hash.split("$")
    if len(parts) != 5 or parts[1] != "pbkdf2-sha256":
        return False
    iterations = int(parts[2])
    salt = bytes.fromhex(parts[3])
    expected = bytes.fromhex(parts[4])
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return dk == expected


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


def dispatch(args: argparse.Namespace) -> int:
    # Parse ws_master_cmd
    cmd = args.ws_master_cmd
    if cmd == "user":
        return _dispatch_user(args)
    if cmd == "pat":
        return _dispatch_pat(args)
    if cmd == "ws":
        return _dispatch_ws(args)
    if cmd == "identity":
        return _dispatch_identity(args)
    print(f"Unknown command: {cmd}", file=sys.stderr)
    return 2


# ---------------------------------------------------------------------------
# user
# ---------------------------------------------------------------------------


def _dispatch_user(args: argparse.Namespace) -> int:
    config, conn = _load_config_and_db(args)
    user_repo = UserRepo(conn)
    ws_repo = WsContainerRepo(conn)

    if args.user_cmd == "add":
        return _user_add(config, user_repo, ws_repo, args)
    if args.user_cmd == "list":
        return _user_list(user_repo)
    if args.user_cmd == "rm":
        return _user_rm(config, user_repo, ws_repo, args)
    return 2


def _user_add(config: MasterConfig, user_repo: UserRepo, ws_repo: WsContainerRepo, args: argparse.Namespace) -> int:
    name = args.name
    display_name = args.display_name

    # Check user_name format
    if not name.replace("_", "").isalnum():
        print("Error: user_name must be alphanumeric (underscore allowed).", file=sys.stderr)
        return 1

    # Check uniqueness
    if user_repo.get_by_name(name):
        print(f"Error: user '{name}' already exists.", file=sys.stderr)
        return 1

    # Get password
    password = args.password
    if not password:
        import getpass
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm: ")
        if password != confirm:
            print("Error: passwords do not match.", file=sys.stderr)
            return 1

    password_hash = _hash_password(password)
    user = user_repo.add(name, display_name, password_hash)
    print(f"User created: {user.user_id}")

    # Create default ws-container (status=absent)
    short_id = _new_short_id()
    container_name = f"everlingo-{name}-{short_id}"
    host_ws_dir = str(Path(config.host_ws_dir) / name / short_id)
    ws = ws_repo.add(
        user_id=user.user_id,
        container_name=container_name,
        host_workspace_dir=host_ws_dir,
        is_default=True,
    )
    print(f"Default ws-container created: {ws.ws_container_id} (status=absent)")
    return 0


def _new_short_id() -> str:
    import uuid
    return uuid.uuid4().hex[:8]


def _user_list(user_repo: UserRepo) -> int:
    users = user_repo.list_all()
    if not users:
        print("No users.")
        return 0
    print(f"{'user_id':38s} {'user_name':20s} {'display_name':20s} {'created_at':22s}")
    print("-" * 100)
    for u in users:
        print(f"{u.user_id:38s} {u.user_name:20s} {u.user_display_name:20s} {u.created_at:22s}")
    return 0


def _user_rm(config: MasterConfig, user_repo: UserRepo, ws_repo: WsContainerRepo, args: argparse.Namespace) -> int:
    user = user_repo.get_by_name(args.name)
    if not user:
        print(f"Error: user '{args.name}' not found.", file=sys.stderr)
        return 1

    if args.purge:
        # Remove all ws-containers
        containers = ws_repo.list_by_user(user.user_id)
        for ws in containers:
            # Try to remove docker container if exists
            if ws.docker_container_id:
                try:
                    import docker
                    client = docker.from_env()
                    try:
                        container = client.containers.get(ws.docker_container_id)
                        container.stop(timeout=10)
                        container.remove()
                    except docker.errors.NotFound:
                        pass
                except Exception as e:
                    print(f"Warning: docker remove failed for {ws.container_name}: {e}", file=sys.stderr)
            # Remove host directory
            if ws.host_workspace_dir:
                container_dir = host_to_container_ws_path(ws.host_workspace_dir, config)
                if container_dir.exists():
                    shutil.rmtree(str(container_dir), ignore_errors=True)
            ws_repo.delete(ws.ws_container_id)

    user_repo.delete(user.user_id)
    print(f"User '{args.name}' deleted.")
    return 0


# ---------------------------------------------------------------------------
# pat
# ---------------------------------------------------------------------------


def _dispatch_pat(args: argparse.Namespace) -> int:
    config, conn = _load_config_and_db(args)
    user_repo = UserRepo(conn)
    pat_repo = PatRepo(conn)

    if args.pat_cmd == "add":
        return _pat_add(user_repo, pat_repo, args)
    if args.pat_cmd == "list":
        return _pat_list(user_repo, pat_repo, args)
    if args.pat_cmd == "rm":
        return _pat_rm(pat_repo, args)
    return 2


def _pat_add(user_repo: UserRepo, pat_repo: PatRepo, args: argparse.Namespace) -> int:
    user = user_repo.get_by_name(args.user)
    if not user:
        print(f"Error: user '{args.user}' not found.", file=sys.stderr)
        return 1

    plain, hashed = generate_pat()

    # Parse expires
    expires_at = None
    if args.expires:
        if args.expires.endswith("d"):
            from datetime import datetime, timedelta, timezone
            days = int(args.expires[:-1])
            expires_at = (datetime.now(timezone.utc) + timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        else:
            expires_at = args.expires

    pat = pat_repo.add(user.user_id, hashed, args.label, expires_at)
    print(f"PAT created: {pat.id}")
    print(f"Token (show once): {plain}")
    return 0


def _pat_list(user_repo: UserRepo, pat_repo: PatRepo, args: argparse.Namespace) -> int:
    user = user_repo.get_by_name(args.user)
    if not user:
        print(f"Error: user '{args.user}' not found.", file=sys.stderr)
        return 1

    pats = pat_repo.list_by_user(user.user_id)
    if not pats:
        print(f"No PATs for user '{args.user}'.")
        return 0
    print(f"{'id':38s} {'label':20s} {'created_at':22s} {'last_used':22s} {'expires':22s}")
    print("-" * 124)
    for p in pats:
        lu = p.last_used_at or ""
        ex = p.expires_at or ""
        print(f"{p.id:38s} {p.label:20s} {p.created_at:22s} {lu:22s} {ex:22s}")
    return 0


def _pat_rm(pat_repo: PatRepo, args: argparse.Namespace) -> int:
    if pat_repo.delete(args.pat_id):
        print("PAT revoked.")
        return 0
    print(f"Error: PAT '{args.pat_id}' not found.", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# ws
# ---------------------------------------------------------------------------


def _dispatch_ws(args: argparse.Namespace) -> int:
    config, conn = _load_config_and_db(args)
    user_repo = UserRepo(conn)
    ws_repo = WsContainerRepo(conn)

    if args.ws_cmd == "add":
        return _ws_add(config, user_repo, ws_repo, args)
    if args.ws_cmd == "list":
        return _ws_list(user_repo, ws_repo, args)
    if args.ws_cmd == "rm":
        return _ws_rm(config, ws_repo, args)
    if args.ws_cmd == "start":
        return _ws_start(ws_repo, args)
    if args.ws_cmd == "stop":
        return _ws_stop(ws_repo, args)
    if args.ws_cmd == "set-default":
        return _ws_set_default(ws_repo, args)
    return 2


def _ws_add(config: MasterConfig, user_repo: UserRepo, ws_repo: WsContainerRepo, args: argparse.Namespace) -> int:
    user = user_repo.get_by_name(args.user)
    if not user:
        print(f"Error: user '{args.user}' not found.", file=sys.stderr)
        return 1

    # Phase 1: max_ws_per_user = 1
    count = ws_repo.count_by_user(user.user_id)
    if count >= config.max_ws_per_user:
        print(f"Error: user '{args.user}' already has {count} ws-container(s) (max={config.max_ws_per_user}).", file=sys.stderr)
        return 1

    # Determine if this should be default (first ws is always default)
    is_default = count == 0
    short_id = _new_short_id()
    container_name = f"everlingo-{user.user_name}-{short_id}"
    host_ws_dir = str(Path(config.host_ws_dir) / user.user_name / short_id)

    ws = ws_repo.add(
        user_id=user.user_id,
        container_name=container_name,
        host_workspace_dir=host_ws_dir,
        is_default=is_default,
    )
    print(f"ws-container created: {ws.ws_container_id} (status=absent)")
    if is_default:
        print("Set as default.")
    return 0


def _ws_list(user_repo: UserRepo, ws_repo: WsContainerRepo, args: argparse.Namespace) -> int:
    if args.user:
        user = user_repo.get_by_name(args.user)
        if not user:
            print(f"Error: user '{args.user}' not found.", file=sys.stderr)
            return 1
        containers = ws_repo.list_by_user(user.user_id)
    else:
        containers = ws_repo.list_all()

    if not containers:
        print("No ws-containers.")
        return 0
    print(f"{'ws_container_id':38s} {'user_id':38s} {'container_name':35s} {'status':12s} {'default':8s} {'created_at':22s}")
    print("-" * 153)
    for ws in containers:
        dflt = "yes" if ws.is_default else "no"
        print(f"{ws.ws_container_id:38s} {ws.user_id:38s} {ws.container_name:35s} {ws.status:12s} {dflt:8s} {ws.created_at:22s}")
    return 0


def _ws_rm(config: MasterConfig, ws_repo: WsContainerRepo, args: argparse.Namespace) -> int:
    ws = ws_repo.get_by_id(args.ws_id)
    if not ws:
        print(f"Error: ws-container '{args.ws_id}' not found.", file=sys.stderr)
        return 1

    if args.purge:
        if ws.docker_container_id:
            try:
                import docker
                client = docker.from_env()
                try:
                    container = client.containers.get(ws.docker_container_id)
                    container.stop(timeout=10)
                    container.remove()
                except docker.errors.NotFound:
                    pass
            except Exception as e:
                print(f"Warning: docker remove failed: {e}", file=sys.stderr)
        if ws.host_workspace_dir:
            container_dir = host_to_container_ws_path(ws.host_workspace_dir, config)
            if container_dir.exists():
                shutil.rmtree(str(container_dir), ignore_errors=True)

    ws_repo.delete(ws.ws_container_id)
    print(f"ws-container '{args.ws_id}' deleted.")
    return 0


def _ws_start(ws_repo: WsContainerRepo, args: argparse.Namespace) -> int:
    ws = ws_repo.get_by_id(args.ws_id)
    if not ws:
        print(f"Error: ws-container '{args.ws_id}' not found.", file=sys.stderr)
        return 1
    if ws.status not in ("stopped", "absent", "error"):
        print(f"ws-container is in status '{ws.status}', cannot start.")
        return 1
    # For CLI, just update status to starting - actual docker start handled by lifecycle
    ws_repo.update_status(ws.ws_container_id, "starting")
    print(f"ws-container '{args.ws_id}' status set to 'starting'.")
    print("Note: Use daemon mode for actual docker lifecycle management.")
    return 0


def _ws_stop(ws_repo: WsContainerRepo, args: argparse.Namespace) -> int:
    ws = ws_repo.get_by_id(args.ws_id)
    if not ws:
        print(f"Error: ws-container '{args.ws_id}' not found.", file=sys.stderr)
        return 1
    ws_repo.update_status(ws.ws_container_id, "stopped")
    print(f"ws-container '{args.ws_id}' status set to 'stopped'.")
    return 0


def _ws_set_default(ws_repo: WsContainerRepo, args: argparse.Namespace) -> int:
    ws = ws_repo.get_by_id(args.ws_id)
    if not ws:
        print(f"Error: ws-container '{args.ws_id}' not found.", file=sys.stderr)
        return 1
    ws_repo.set_default(ws.ws_container_id, ws.user_id)
    print(f"ws-container '{args.ws_id}' set as default.")
    return 0


# ---------------------------------------------------------------------------
# identity
# ---------------------------------------------------------------------------


def _dispatch_identity(args: argparse.Namespace) -> int:
    config, conn = _load_config_and_db(args)
    user_repo = UserRepo(conn)
    identity_repo = IdentityRepo(conn)

    if args.identity_cmd == "list":
        return _identity_list(user_repo, identity_repo, args)
    if args.identity_cmd == "unlink":
        return _identity_unlink(identity_repo, args)
    return 2


def _identity_list(user_repo: UserRepo, identity_repo: IdentityRepo, args: argparse.Namespace) -> int:
    user = user_repo.get_by_name(args.user)
    if not user:
        print(f"Error: user '{args.user}' not found.", file=sys.stderr)
        return 1

    identities = identity_repo.list_by_user(user.user_id)
    if not identities:
        print(f"No external identities for user '{args.user}'.")
        return 0
    print(f"{'identity_id':38s} {'provider':12s} {'subject':40s} {'email':30s} {'last_used':22s}")
    print("-" * 142)
    for i in identities:
        lu = i.last_used_at or ""
        em = i.email or ""
        print(f"{i.identity_id:38s} {i.provider:12s} {i.subject:40s} {em:30s} {lu:22s}")
    return 0


def _identity_unlink(identity_repo: IdentityRepo, args: argparse.Namespace) -> int:
    if identity_repo.unlink(args.identity_id):
        print("Identity unlinked.")
        return 0
    print(f"Error: identity '{args.identity_id}' not found.", file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Main entry (for direct python -m everlingo.ws_master)
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI main entry, invoked from main.py dispatch or __main__.py."""
    # Parse --config first if present (for db path)
    parser = _build_parser()
    # Inject --config at top level
    parser.add_argument("--config", default=None, help="配置文件路径")
    args = parser.parse_args()
    sys.exit(dispatch(args))


if __name__ == "__main__":
    main()