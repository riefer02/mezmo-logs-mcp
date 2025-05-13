from mcp.server.fastmcp import FastMCP
from typing import Optional, List
from memo_api import fetch_latest_logs

mcp = FastMCP("Mezmo Log MCP")


@mcp.tool()
async def get_logs(
    count: Optional[int] = 50,
    apps: Optional[str] = None,
    hosts: Optional[str] = None,
    levels: Optional[str] = None,
    query: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    prefer: Optional[str] = "tail",
    pagination_id: Optional[str] = None,
) -> List[dict]:
    """
    Retrieve logs from Mezmo Export API v2.
    Parameters:
        count (Optional[int]): Number of logs to return (max 10,000, default 50)
        apps (Optional[str]): Comma-separated list of applications
        hosts (Optional[str]): Comma-separated list of hosts
        levels (Optional[str]): Comma-separated list of log levels
        query (Optional[str]): Search query
        from_ts (Optional[str]): Start time (UNIX timestamp, seconds or ms)
        to_ts (Optional[str]): End time (UNIX timestamp, seconds or ms)
        prefer (Optional[str]): 'head' or 'tail' (default: 'tail')
        pagination_id (Optional[str]): Token for paginated results
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
