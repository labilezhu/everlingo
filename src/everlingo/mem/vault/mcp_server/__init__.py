"""vault MCP server subpackage.

ref: docs/impl-spec/vault-mcp/valut-mcp-spec.md
MCP 2025-11-25 Streamable HTTP server embedded in the indexer process, exposing
fs tools + search tool + session.configure. URL is written to
$workspace/indexer.mcp.url at indexer startup.
"""

from .mcp_server import (
    PathEscapeError,
    SessionRegistry,
    SessionState,
    create_mcp_app,
    pick_free_port,
    resolve_vault_path,
    run_mcp_server,
)

__all__ = [
    "PathEscapeError",
    "SessionRegistry",
    "SessionState",
    "create_mcp_app",
    "pick_free_port",
    "resolve_vault_path",
    "run_mcp_server",
]

