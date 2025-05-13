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
    app_name: Optional[str] = None,
    query: Optional[str] = None,
) -> List[dict]:
    """
    Fetch the latest logs from Mezmo Export API v2.
    Returns a list of log lines (as dicts).
    """
    url = f"{MEZMO_API_BASE_URL}/v2/export"
    params = {
        "from": 0,  # retention boundary
        "to": 0,  # now
        "size": count,
        "prefer": "tail",
    }
    if app_name:
        params["apps"] = app_name
    if query:
        params["query"] = query

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
