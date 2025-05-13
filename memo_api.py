import os
import httpx
import asyncio
from typing import Optional, List
from dotenv import load_dotenv

load_dotenv()

MEZMO_API_KEY = os.getenv("MEZMO_API_KEY")
MEZMO_API_BASE_URL = os.getenv("MEZMO_API_BASE_URL", "https://api.mezmo.com")

if not MEZMO_API_KEY:
    raise RuntimeError("MEZMO_API_KEY is not set in environment variables.")


async def fetch_latest_logs(
    count: int = 50,
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
    Fetch logs from Mezmo Export API v2.
    Parameters:
        count (int): Number of logs to return (max 10,000)
        apps (str, optional): Comma-separated list of applications
        hosts (str, optional): Comma-separated list of hosts
        levels (str, optional): Comma-separated list of log levels
        query (str, optional): Search query
        from_ts (str, optional): Start time (UNIX timestamp)
        to_ts (str, optional): End time (UNIX timestamp)
        prefer (str, optional): 'head' or 'tail' (default: 'tail')
        pagination_id (str, optional): Token for paginated results
    Returns:
        List of log lines (as dicts)
    """
    url = f"{MEZMO_API_BASE_URL}/v2/export"
    params = {
        "from": from_ts if from_ts is not None else 0,  # retention boundary
        "to": to_ts if to_ts is not None else 0,  # now
        "size": count,
        "prefer": prefer,
    }
    if apps:
        params["apps"] = apps
    if hosts:
        params["hosts"] = hosts
    if levels:
        params["levels"] = levels
    if query:
        params["query"] = query
    if pagination_id:
        params["pagination_id"] = pagination_id

    headers = {"servicekey": MEZMO_API_KEY}

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            resp = await client.get(url, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("lines", [])
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Mezmo API error: {e.response.status_code} {e.response.text}"
            )
        except Exception as e:
            raise RuntimeError(f"Failed to fetch logs from Mezmo: {e}")
