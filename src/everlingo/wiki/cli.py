from __future__ import annotations

import argparse
from pathlib import Path

from .. import workspace
from .builder import wiki_build, wiki_serve, _DEFAULT_DIST_DIR


def cmd_build(args: argparse.Namespace) -> int:
    ws = workspace.current_workspace()
    dist = Path(args.dist) if args.dist else ws / _DEFAULT_DIST_DIR
    wiki_build(workspace_path=ws, dist_dir=dist)
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    ws = workspace.current_workspace()
    dist = Path(args.dist) if args.dist else ws / _DEFAULT_DIST_DIR
    wiki_serve(dist, port=args.port)
    return 0
