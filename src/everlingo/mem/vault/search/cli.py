# ref: docs/impl-spec/search/memory-vault-search-spec.md — 索引维护 CLI
# 一次性手动维护工具，全部经 HTTP 委托 indexer 服务，不直接打开 SQLite。
#
# 命令：
#   indexer start            在当前进程前台启动 indexer（阻塞，Ctrl-C 退出）
#   indexer status           GET /status
#   reindex [PATH]           POST /index 批量投递
#   reindex --rebuild        POST /rebuild
#
# Workspace 选择：--workspace-dir / -w/--workspace / EVERLINGO_WORKSPACE_DIR /
# EVERLINGO_WORKSPACE / default；与 gateway 入口一致。

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .... import workspace
from .client import SearchClient

logger = logging.getLogger(__name__)


# ── indexer status / reindex 委托给 running indexer ─────────────────


def _resolve_workspace(args: argparse.Namespace) -> Path:
    """把 CLI 参数应用到 workspace 模块，返回 ws 根目录。"""
    if getattr(args, "workspace_dir", None) is not None:
        workspace.init_workspace_dir(args.workspace_dir)
    elif getattr(args, "workspace", None) is not None:
        workspace.init_workspace(args.workspace)
    return workspace.current_workspace()


def _client() -> SearchClient:
    return SearchClient(workspace.indexer_socket_path())


def _require_indexer_alive(client: SearchClient) -> bool:
    s = client.status()
    return s is not None and s.running


def cmd_indexer_start(args: argparse.Namespace) -> int:
    """在当前进程前台运行 indexer（阻塞）。日志写 $workspace/logs/indexer.log。"""
    ws = _resolve_workspace(args)
    socket_path = workspace.indexer_socket_path()
    if socket_path.exists():
        # 检查是否真的在跑
        s = _client().status()
        if s is not None:
            print(f"indexer 已在运行: {socket_path} (docs={s.docs}, chunks={s.chunks})")
            return 0
        # socket 文件存在但 indexer 不在 -> 清理
        try:
            socket_path.unlink()
        except OSError as e:
            print(f"无法删除旧 socket {socket_path}: {e}", file=sys.stderr)
            return 1
    log_path = ws / "logs" / "indexer.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"indexer 启动（前台）：socket={socket_path} log={log_path}")
    from .server import _run_indexer

    return _run_indexer(args.log_level, log_path)


def cmd_indexer_status(args: argparse.Namespace) -> int:
    _resolve_workspace(args)
    client = _client()
    s = client.status()
    if s is None:
        print("indexer 未运行", file=sys.stderr)
        return 1
    print(json.dumps(s.model_dump(), ensure_ascii=False, indent=2))
    return 0


def cmd_embed(args: argparse.Namespace) -> int:
    """经 HTTP 触发 indexer 跑一轮 embedding 补嵌。"""
    _resolve_workspace(args)
    client = _client()
    if not _require_indexer_alive(client):
        print(
            f"indexer 未运行，请先 `everlingo mem indexer start` (socket={workspace.indexer_socket_path()})",
            file=sys.stderr,
        )
        return 1
    resp = client.embed(rebuild=args.rebuild, batch=args.batch, wait=not args.fire_and_forget)
    if resp is None:
        print("embed 调用失败", file=sys.stderr)
        return 1
    if not resp.ok:
        print(
            "embedder 未启用（OPENAI_EMBEDDING_MODEL 未配）；向量检索不可用",
            file=sys.stderr,
        )
        return 1
    if args.rebuild:
        print(
            f"rebuild 嵌入: total={resp.total_chunks} embedded={resp.embedded_chunks} "
            f"model_id={resp.embedding_model_id} dim={resp.embedding_dim} took_ms={resp.took_ms:.1f}"
        )
    else:
        print(
            f"embed: total={resp.total_chunks} embedded={resp.embedded_chunks} "
            f"model_id={resp.embedding_model_id} dim={resp.embedding_dim} took_ms={resp.took_ms:.1f}"
        )
    return 0


def cmd_reindex(args: argparse.Namespace) -> int:
    _resolve_workspace(args)
    client = _client()
    if not _require_indexer_alive(client):
        print(
            f"indexer 未运行，请先 `everlingo mem indexer start` (socket={workspace.indexer_socket_path()})",
            file=sys.stderr,
        )
        return 1

    if args.rebuild:
        resp = client.rebuild()
        if resp is None:
            print("rebuild 失败", file=sys.stderr)
            return 1
        print(
            f"rebuild ok: indexed={resp.indexed} chunks={resp.chunks} took_ms={resp.took_ms:.1f}"
        )
        return 0

    # 增量：扫描 PATH 或全 vault，逐个 POST /index
    memory_root = workspace.memory_dir()
    if not memory_root.exists():
        print(f"memory 目录不存在: {memory_root}", file=sys.stderr)
        return 1

    target = args.path
    if target is None:
        files = sorted(memory_root.rglob("*.md"))
    else:
        p = (memory_root / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
        if p.is_file() and p.suffix == ".md":
            files = [p]
        elif p.is_dir():
            files = sorted(p.rglob("*.md"))
        else:
            print(f"PATH 既不是文件也不是目录: {target}", file=sys.stderr)
            return 1

    indexed = 0
    failed = 0
    for f in files:
        rel = f.resolve().relative_to(memory_root.resolve()).as_posix()
        if client.index_file(rel):
            indexed += 1
            if args.verbose:
                print(f"  indexed: {rel}")
        else:
            failed += 1
            print(f"  FAILED: {rel}", file=sys.stderr)

    print(f"reindex done: ok={indexed} failed={failed} total={len(files)}")
    return 0 if failed == 0 else 1


# ── argparse 子命令装配 ─────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="everlingo mem",
        description="everlingo memory vault search 索引维护",
    )
    ws_group = parser.add_mutually_exclusive_group()
    ws_group.add_argument("-w", "--workspace", default=None, help="workspace 名（~/.everlingo/workspaces/<name>/）")
    ws_group.add_argument("--workspace-dir", default=None, help="workspace 根目录任意路径")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_idx_start = sub.add_parser("indexer", help="indexer 进程控制")
    p_idx_sub = p_idx_start.add_subparsers(dest="indexer_cmd", required=True)
    p_start = p_idx_sub.add_parser("start", help="前台启动 indexer（阻塞，Ctrl-C 退出）")
    p_start.add_argument("--log-level", default="info")
    p_start.set_defaults(func=cmd_indexer_start)
    p_status = p_idx_sub.add_parser("status", help="查询 indexer 状态")
    p_status.set_defaults(func=cmd_indexer_status)

    p_reindex = sub.add_parser("reindex", help="增量刷新或全量重建")
    p_reindex.add_argument("path", nargs="?", default=None, help="文件或目录路径（相对 $workspace/memory）；省略=全 vault")
    p_reindex.add_argument("--rebuild", action="store_true", help="完全删除 index，从零重建")
    p_reindex.add_argument("-v", "--verbose", action="store_true", help="逐文件输出")
    p_reindex.set_defaults(func=cmd_reindex)

    p_embed = sub.add_parser("embed", help="补嵌/重建 embedding")
    p_embed.add_argument("--rebuild", action="store_true", help="drop 旧 vec0+embeddings，全量重嵌")
    p_embed.add_argument("--batch", type=int, default=64, help="每批嵌入 chunk 数（默认 64）")
    p_embed.add_argument(
        "--fire-and-forget",
        action="store_true",
        help="触发后立即返回，不等待嵌入完成",
    )
    p_embed.set_defaults(func=cmd_embed)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
