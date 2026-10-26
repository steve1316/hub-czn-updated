"""
Stdio MCP server that lets a coding agent drive the running Hub CZN sidecar.

Dev tool only. It is not bundled into the PyInstaller sidecar. See README.md for registration.
"""
import sys
from pathlib import Path

from mcp.server.mcpserver import MCPServer

sys.path.insert(0, str(Path(__file__).resolve().parent))
import hub_tools as tools

mcp = MCPServer("hub-czn")
client = tools.HubClient()


@mcp.tool()
def capture_status() -> dict:
    """Whether capture is running, plus region, admin flag and rescue file."""
    return tools.capture_status(client)


@mcp.tool()
def capture_start(region: str = "global", debug: bool = False) -> dict:
    """Start capture. `region` is "global" or "asia". Needs an elevated sidecar."""
    return tools.capture_start(client, region, debug)


@mcp.tool()
def capture_stop() -> dict:
    """Stop capture and restore the hosts file."""
    return tools.capture_stop(client)


@mcp.tool()
def setup_status() -> dict:
    """Prerequisite checks: admin, mitmproxy, certificate, hosts redirect."""
    return tools.setup_status(client)


@mcp.tool()
def latest_snapshot(limit: int = 20) -> dict:
    """Loaded snapshot status, a count summary, and the first `limit` memory fragments."""
    return tools.latest_snapshot(client, limit)


@mcp.tool()
def rescue_records():
    """Processed rescue records from the latest rescue snapshot."""
    return tools.rescue_records(client)


@mcp.tool()
def capture_log_tail(n: int = 50) -> dict:
    """The last `n` capture log lines (1-500), oldest first."""
    return tools.capture_log_tail(client, n)


@mcp.tool()
def replay_capture(path: str | None = None) -> dict:
    """Replay a saved battle capture through the simulator and return the report path and summary."""
    return tools.replay_capture(path)


if __name__ == "__main__":
    mcp.run()
