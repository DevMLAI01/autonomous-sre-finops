"""
Node 1 — Investigator Agent
Queries AWS via MCP to find underutilized, costly EC2 instances.
"""
from __future__ import annotations

import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from graph.state import OrchestratorState
from config import cfg


async def investigate(state: OrchestratorState) -> OrchestratorState:
    """LangGraph node: discover underutilized AWS resources."""
    print("[investigator] Scanning AWS for underutilized resources...")
    errors = list(state.get("errors", []))

    try:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_servers.aws_mcp_server"],
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                result = await session.call_tool(
                    "find_underutilized_resources",
                    arguments={
                        "cpu_threshold": cfg.CPU_UTILIZATION_THRESHOLD,
                        "cost_threshold": cfg.MONTHLY_COST_THRESHOLD,
                        "lookback_days": cfg.LOOKBACK_DAYS,
                    },
                )

                data = json.loads(result.content[0].text)
                flagged = data.get("flagged_resources", [])

        summary = (
            f"Found {len(flagged)} underutilized resource(s) "
            f"(CPU < {cfg.CPU_UTILIZATION_THRESHOLD}%, cost > ${cfg.MONTHLY_COST_THRESHOLD}/mo, "
            f"lookback {cfg.LOOKBACK_DAYS}d)."
        )
        print(f"[investigator] {summary}")

        return {
            **state,
            "flagged_resources": flagged,
            "investigation_summary": summary,
            "resource_index": 0,
            "errors": errors,
        }

    except Exception as e:
        # Unwrap Python 3.11+ ExceptionGroup raised by asyncio TaskGroup in MCP client
        if hasattr(e, 'exceptions') and e.exceptions:
            e = e.exceptions[0]
        msg = f"[investigator] FAILED: {type(e).__name__}: {e}"
        print(msg)
        return {
            **state,
            "flagged_resources": [],
            "investigation_summary": f"Investigation failed: {e}",
            "resource_index": 0,
            "decision": "DONE",
            "errors": errors + [msg],
        }
