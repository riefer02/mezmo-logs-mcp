from mcp.server.fastmcp import FastMCP
from typing import Optional
from memo_api import fetch_latest_logs

mcp = FastMCP("Mezmo Log MCP")


@mcp.tool()
async def get_latest_logs(
    count: int = 50,
    app_name: Optional[str] = None,
    query: Optional[str] = None,
) -> list:
    """
    Retrieve the latest N logs from Mezmo. Optionally filter by app name and query.
    """
    try:
        logs = await fetch_latest_logs(count=count, app_name=app_name, query=query)
        return logs
    except Exception as e:
        return [{"error": str(e)}]


if __name__ == "__main__":
    mcp.run()
