# ref: docs/impl-spec/search/memory-vault-search-spec.md — 索引维护 CLI
# 一次性手动维护工具，全部经 HTTP 委托 indexer 服务，不直接打开 SQLite。
#
# 命令：
#   indexer start            在当前进程前台启动 indexer（阻塞，Ctrl-C 退出）
#   indexer status           GET /status
#   reindex LANG [PATH]      POST /{lang}/index 批量投递
#   reindex LANG --rebuild   POST /{lang}/rebuild
#   embed [LANG]             POST /{lang}/embed
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
from .indexer import is_excluded_vault_file

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
            langs_info = ", ".join(f"{l.lang}={l.docs}docs" for l in s.langs)
            print(f"indexer 已在运行: {socket_path} ({langs_info})")
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

    lang = getattr(args, "lang", None)
    if lang:
        resp = client.embed(lang, rebuild=args.rebuild, batch=args.batch, wait=not args.fire_and_forget)
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
                f"[{lang}] rebuild 嵌入: total={resp.total_chunks} embedded={resp.embedded_chunks} "
                f"model_id={resp.embedding_model_id} dim={resp.embedding_dim} took_ms={resp.took_ms:.1f}"
            )
        else:
            print(
                f"[{lang}] embed: total={resp.total_chunks} embedded={resp.embedded_chunks} "
                f"model_id={resp.embedding_model_id} dim={resp.embedding_dim} took_ms={resp.took_ms:.1f}"
            )
        return 0

    # 无 lang 参数：对所有 lang 依次执行
    langs = workspace.lang_dirs()
    if not langs:
        print("workspace 下没有已配置的语言目录 (memory/languages/*/)", file=sys.stderr)
        return 1
    for l in langs:
        resp = client.embed(l, rebuild=args.rebuild, batch=args.batch, wait=not args.fire_and_forget)
        if resp is None:
            print(f"[{l}] embed 调用失败", file=sys.stderr)
            continue
        if not resp.ok:
            print(f"[{l}] embedder 未启用", file=sys.stderr)
            continue
        print(
            f"[{l}] embed: total={resp.total_chunks} embedded={resp.embedded_chunks} "
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

    lang = args.lang

    if args.rebuild:
        resp = client.rebuild(lang)
        if resp is None:
            print(f"[{lang}] rebuild 失败", file=sys.stderr)
            return 1
        print(
            f"[{lang}] rebuild ok: indexed={resp.indexed} chunks={resp.chunks} took_ms={resp.took_ms:.1f}"
        )
        return 0

    # 增量：扫描 PATH 或全 lang vault，逐个 POST /{lang}/index
    memory_root = workspace.lang_vault_dir(lang)
    if not memory_root.exists():
        print(f"语言 vault 目录不存在: {memory_root}", file=sys.stderr)
        return 1

    target = args.path
    if target is None:
        files = sorted(memory_root.rglob("*.md"))
        files = [f for f in files if not is_excluded_vault_file(f, memory_root)]
    else:
        p = (memory_root / target).resolve() if not Path(target).is_absolute() else Path(target).resolve()
        if p.is_file() and p.suffix == ".md":
            files = [p]
        elif p.is_dir():
            files = sorted(p.rglob("*.md"))
            files = [f for f in files if not is_excluded_vault_file(f, memory_root)]
        else:
            print(f"PATH 既不是文件也不是目录: {target}", file=sys.stderr)
            return 1

    indexed = 0
    failed = 0
    for f in files:
        rel = f.resolve().relative_to(memory_root.resolve()).as_posix()
        if client.index_file(lang, rel):
            indexed += 1
            if args.verbose:
                print(f"  indexed: {rel}")
        else:
            failed += 1
            print(f"  FAILED: {rel}", file=sys.stderr)

    print(f"[{lang}] reindex done: ok={indexed} failed={failed} total={len(files)}")
    return 0 if failed == 0 else 1


# ── argparse 子命令装配 ─────────────────────────────────────────────


def _require_indexer(client: SearchClient) -> bool:
    return _require_indexer_alive(client)


def _fmt_push_result(ok, done: bool) -> str:
    if not done:
        return "indexer 不可达 / 调用失败"
    return "push 成功" if ok else "push 失败（远端被更新或网络错误）"


def cmd_version_status(args: argparse.Namespace) -> int:
    """mem status → GET /version/status。"""
    _resolve_workspace(args)
    resp = _client().version_status()
    if resp is None:
        print("indexer 未运行 / 不可达", file=sys.stderr)
        return 1
    print(json.dumps(resp.model_dump(), ensure_ascii=False, indent=2))
    return 0


def cmd_version_snapshot(args: argparse.Namespace) -> int:
    """mem snapshot → POST /version/commit。"""
    _resolve_workspace(args)
    if not _require_indexer_alive(_client()):
        print("indexer 未运行，无法 snapshot", file=sys.stderr)
        return 1
    ok = _client().version_commit()
    print("commit 成功" if ok else ("无变更，未产生 commit" if ok is False else "commit 调用失败"))
    return 0 if ok is not None else 1


def cmd_version_push(args: argparse.Namespace) -> int:
    """mem push → POST /version/push。"""
    _resolve_workspace(args)
    if not _require_indexer_alive(_client()):
        print("indexer 未运行，无法 push", file=sys.stderr)
        return 1
    ok = _client().version_push()
    if ok is None:
        print("push 调用失败", file=sys.stderr)
        return 1
    print("push 成功" if ok else "push 失败")
    return 0 if ok else 1


def cmd_version_pull(args: argparse.Namespace) -> int:
    """mem pull → POST /version/pull（commit→fetch→rebase）。"""
    _resolve_workspace(args)
    if not _require_indexer_alive(_client()):
        print("indexer 未运行，无法 pull", file=sys.stderr)
        return 1
    resp = _client().version_pull()
    if resp is None:
        print("pull 调用失败", file=sys.stderr)
        return 1
    if resp.ok:
        print(f"pull ok: {resp.message}")
        return 0
    print(f"pull 有冲突，共 {len(resp.conflicts)} 个冲突文件", file=sys.stderr)
    for f in resp.conflicts[:20]:
        print(f"  {f}", file=sys.stderr)
    if resp.backup_branch:
        print(f"本地状态已备份到分支: {resp.backup_branch}", file=sys.stderr)
    print("如需强制以远端为准，请再次运行 `everlingo mem pull --hard`", file=sys.stderr)
    return 1


def cmd_version_log(args: argparse.Namespace) -> int:
    """mem log [--limit N] → GET /version/log。"""
    _resolve_workspace(args)
    resp = _client().version_log(limit=args.limit)
    if resp is None:
        print("indexer 未运行 / 不可达", file=sys.stderr)
        return 1
    if not resp.commits:
        print("（暂无 commit）")
        return 0
    for c in resp.commits:
        print(f"{c.hash[:10]}  {c.time}  {c.message}")
    return 0


def cmd_version_restore(args: argparse.Namespace) -> int:
    """mem restore [--hard] COMMIT → POST /version/restore 或 pull --hard。"""
    _resolve_workspace(args)
    client = _client()
    if not _require_indexer_alive(client):
        print("indexer 未运行，无法 restore", file=sys.stderr)
        return 1
    if args.hard:
        resp = client.version_pull()  # restore --hard 走 pull 的 hard reset
        if resp is None:
            print("restore 调用失败", file=sys.stderr)
            return 1
        print(resp.message)
        return 0 if resp.ok else 1
    resp = client.version_restore(args.commit_hash)
    if resp is None:
        print("restore 调用失败", file=sys.stderr)
        return 1
    print(resp.message)
    return 0 if resp.ok else 1


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
    p_reindex.add_argument("lang", help="目标学习语言编码（如 en, ja）")
    p_reindex.add_argument("path", nargs="?", default=None, help="文件或目录路径（相对 $workspace/memory/languages/$lang/vault）；省略=全 lang vault")
    p_reindex.add_argument("--rebuild", action="store_true", help="完全删除 index，从零重建")
    p_reindex.add_argument("-v", "--verbose", action="store_true", help="逐文件输出")
    p_reindex.set_defaults(func=cmd_reindex)

    p_embed = sub.add_parser("embed", help="补嵌/重建 embedding")
    p_embed.add_argument("lang", nargs="?", default=None, help="目标学习语言编码；省略则对所有语言执行")
    p_embed.add_argument("--rebuild", action="store_true", help="drop 旧 vec0+embeddings，全量重嵌")
    p_embed.add_argument("--batch", type=int, default=64, help="每批嵌入 chunk 数（默认 64）")
    p_embed.add_argument(
        "--fire-and-forget",
        action="store_true",
        help="触发后立即返回，不等待嵌入完成",
    )
    p_embed.set_defaults(func=cmd_embed)

    # Memory Vault 版本控制
    p_vstatus = sub.add_parser("vstatus", help="Memory Vault 版本控制状态")
    p_vstatus.set_defaults(func=cmd_version_status)
    p_snap = sub.add_parser("snapshot", help="同步触发一次 commit（快照）")
    p_snap.set_defaults(func=cmd_version_snapshot)
    p_push = sub.add_parser("push", help="手动 push --force-with-lease 到远端")
    p_push.set_defaults(func=cmd_version_push)
    p_pull = sub.add_parser("pull", help="从远端恢复（commit→fetch→rebase）")
    p_pull.set_defaults(func=cmd_version_pull)
    p_log = sub.add_parser("log", help="查看历史 commit 列表")
    p_log.add_argument("--limit", type=int, default=20)
    p_log.set_defaults(func=cmd_version_log)
    p_restore = sub.add_parser("restore", help="把指定历史版本检出到 backup 分支")
    p_restore.add_argument("commit_hash", help="目标 commit（hash 前缀或完整 hash）")
    p_restore.set_defaults(func=cmd_version_restore)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
