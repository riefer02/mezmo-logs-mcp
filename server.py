from mcp.server.fastmcp import FastMCP
from typing import List
from memo_api import fetch_latest_logs

mcp = FastMCP("Mezmo Log MCP")


@mcp.tool()
async def get_logs(
    count: int = 50,
    apps: str = None,
    hosts: str = None,
    levels: str = None,
    query: str = None,
    from_ts: str = None,
    to_ts: str = None,
    prefer: str = "tail",
    pagination_id: str = None,
) -> List[dict]:
    """
    Retrieve logs from Mezmo Export API v2.
    Parameters:
        count (int): Number of logs to return (max 10,000, default 50)
        apps (str): Comma-separated list of applications
        hosts (str): Comma-separated list of hosts
        levels (str): Comma-separated list of log levels
        query (str): Search query
        from_ts (str): Start time (UNIX timestamp, seconds or ms)
        to_ts (str): End time (UNIX timestamp, seconds or ms)
        prefer (str): 'head' or 'tail' (default: 'tail')
        pagination_id (str): Token for paginated results
    Returns:
        List[dict]: List of log lines (raw format)
    """
    try:
        logs = await fetch_latest_logs(
            count=count,
            apps=apps,
            hosts=hosts,
            levels=levels,
            query=query,
            from_ts=from_ts,
            to_ts=to_ts,
            prefer=prefer,
            pagination_id=pagination_id,
        )
        return logs
    except Exception as e:
        return [{"error": str(e)}]


if __name__ == "__main__":
    mcp.run()
