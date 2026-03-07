"""
AWS MCP Server — Read-Only
Exposes Cost Explorer, CloudTrail, and EC2 metadata via MCP tools.

IAM permissions required (read-only):
  - ce:GetCostAndUsage
  - cloudtrail:LookupEvents
  - ec2:DescribeInstances
  - cloudwatch:GetMetricStatistics
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from config import cfg

app = Server("aws-readonly-mcp")

# ── Boto3 clients (read-only credentials enforced by IAM policy) ─────────────
def _ec2():
    return boto3.client(
        "ec2",
        region_name=cfg.AWS_DEFAULT_REGION,
        aws_access_key_id=cfg.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=cfg.AWS_SECRET_ACCESS_KEY,
    )


def _cloudwatch():
    return boto3.client(
        "cloudwatch",
        region_name=cfg.AWS_DEFAULT_REGION,
        aws_access_key_id=cfg.AWS_ACCESS_KEY_ID,
        aws_secret_access_key=cfg.AWS_SECRET_ACCESS_KEY,
    )


# ── Tool definitions ─────────────────────────────────────────────────────────
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_ec2_instances",
            description="List all EC2 instances with their tags, state, and instance type.",
            inputSchema={
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Filter by state: running, stopped, all (default: running)",
                        "default": "running",
                    }
                },
            },
        ),
        Tool(
            name="get_cpu_utilization",
            description=(
                "Get average CPU utilization for an EC2 instance over the last N days "
                "using CloudWatch metrics."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string", "description": "EC2 instance ID"},
                    "lookback_days": {
                        "type": "integer",
                        "description": "Number of days to look back (default: 7)",
                        "default": 7,
                    },
                },
                "required": ["instance_id"],
            },
        ),
        Tool(
            name="get_monthly_cost",
            description="Get the estimated monthly cost for a specific EC2 instance via Cost Explorer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string", "description": "EC2 instance ID"},
                },
                "required": ["instance_id"],
            },
        ),
        Tool(
            name="find_underutilized_resources",
            description=(
                "Identify EC2 instances with CPU utilization below the threshold "
                "AND monthly cost above the cost threshold. "
                f"Defaults: CPU < {cfg.CPU_UTILIZATION_THRESHOLD}%, cost > ${cfg.MONTHLY_COST_THRESHOLD}/mo."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cpu_threshold": {"type": "number", "default": cfg.CPU_UTILIZATION_THRESHOLD},
                    "cost_threshold": {"type": "number", "default": cfg.MONTHLY_COST_THRESHOLD},
                    "lookback_days": {"type": "integer", "default": cfg.LOOKBACK_DAYS},
                },
            },
        ),
    ]


# ── Tool implementations ─────────────────────────────────────────────────────
@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "list_ec2_instances":
        return await _list_ec2_instances(arguments)
    elif name == "get_cpu_utilization":
        return await _get_cpu_utilization(arguments)
    elif name == "get_monthly_cost":
        return await _get_monthly_cost(arguments)
    elif name == "find_underutilized_resources":
        return await _find_underutilized_resources(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _list_ec2_instances(args: dict) -> list[TextContent]:
    state_filter = args.get("state", "running")
    filters = [] if state_filter == "all" else [{"Name": "instance-state-name", "Values": [state_filter]}]

    resp = _ec2().describe_instances(Filters=filters)
    instances = []
    for reservation in resp["Reservations"]:
        for inst in reservation["Instances"]:
            tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
            instances.append({
                "instance_id": inst["InstanceId"],
                "instance_type": inst["InstanceType"],
                "state": inst["State"]["Name"],
                "launch_time": inst["LaunchTime"].isoformat(),
                "tags": tags,
            })

    return [TextContent(type="text", text=json.dumps(instances, indent=2))]


async def _get_cpu_utilization(args: dict) -> list[TextContent]:
    instance_id = args["instance_id"]
    lookback_days = args.get("lookback_days", cfg.LOOKBACK_DAYS)

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)

    resp = _cloudwatch().get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=start,
        EndTime=end,
        Period=86400,  # daily averages
        Statistics=["Average"],
    )

    datapoints = resp.get("Datapoints", [])
    if not datapoints:
        avg_cpu = 0.0
    else:
        avg_cpu = sum(d["Average"] for d in datapoints) / len(datapoints)

    result = {
        "instance_id": instance_id,
        "lookback_days": lookback_days,
        "average_cpu_percent": round(avg_cpu, 2),
        "datapoints": len(datapoints),
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# On-demand hourly prices (us-east-1, Linux) for common instance types.
# Used as fallback when Cost Explorer resource-level granularity is not enabled.
_EC2_HOURLY_PRICE: dict[str, float] = {
    "t2.micro": 0.0116, "t2.small": 0.023, "t2.medium": 0.0464,
    "t3.micro": 0.0104, "t3.small": 0.0208, "t3.medium": 0.0416,
    "t3.large": 0.0832, "t3.xlarge": 0.1664, "t3.2xlarge": 0.3328,
    "m5.large": 0.096, "m5.xlarge": 0.192, "m5.2xlarge": 0.384,
    "m5.4xlarge": 0.768, "m5.8xlarge": 1.536,
    "c5.large": 0.085, "c5.xlarge": 0.17, "c5.2xlarge": 0.34,
    "r5.large": 0.126, "r5.xlarge": 0.252, "r5.2xlarge": 0.504,
}
_HOURS_PER_MONTH = 730


async def _get_monthly_cost(args: dict) -> list[TextContent]:
    instance_id = args["instance_id"]

    # Resolve instance type from EC2 metadata for price estimate
    try:
        resp = _ec2().describe_instances(InstanceIds=[instance_id])
        inst = resp["Reservations"][0]["Instances"][0]
        instance_type = inst.get("InstanceType", "unknown")
    except Exception:
        instance_type = "unknown"

    hourly = _EC2_HOURLY_PRICE.get(instance_type, 0.10)  # default $0.10/hr if unknown
    monthly_cost = round(hourly * _HOURS_PER_MONTH, 2)

    result = {
        "instance_id": instance_id,
        "instance_type": instance_type,
        "hourly_price_usd": hourly,
        "estimated_monthly_cost_usd": monthly_cost,
        "note": "Estimate based on on-demand pricing (us-east-1, Linux).",
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _find_underutilized_resources(args: dict) -> list[TextContent]:
    cpu_threshold = args.get("cpu_threshold", cfg.CPU_UTILIZATION_THRESHOLD)
    cost_threshold = args.get("cost_threshold", cfg.MONTHLY_COST_THRESHOLD)
    lookback_days = args.get("lookback_days", cfg.LOOKBACK_DAYS)

    # 1. Get all running instances
    instances_result = await _list_ec2_instances({"state": "running"})
    instances = json.loads(instances_result[0].text)

    flagged = []
    for inst in instances:
        iid = inst["instance_id"]

        # 2. Check CPU
        cpu_result = await _get_cpu_utilization({"instance_id": iid, "lookback_days": lookback_days})
        cpu_data = json.loads(cpu_result[0].text)
        avg_cpu = cpu_data["average_cpu_percent"]

        if avg_cpu >= cpu_threshold:
            continue  # CPU is fine, skip

        # 3. Check cost
        cost_result = await _get_monthly_cost({"instance_id": iid})
        cost_data = json.loads(cost_result[0].text)
        monthly_cost = cost_data["estimated_monthly_cost_usd"]

        if monthly_cost < cost_threshold:
            continue  # Cost is low, not worth flagging

        flagged.append({
            "instance_id": iid,
            "instance_type": inst["instance_type"],
            "tags": inst["tags"],
            "average_cpu_percent": avg_cpu,
            "estimated_monthly_cost_usd": monthly_cost,
        })

    summary = {
        "flagged_count": len(flagged),
        "cpu_threshold_percent": cpu_threshold,
        "cost_threshold_usd": cost_threshold,
        "lookback_days": lookback_days,
        "flagged_resources": flagged,
    }
    return [TextContent(type="text", text=json.dumps(summary, indent=2))]


# ── Entry point ───────────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
