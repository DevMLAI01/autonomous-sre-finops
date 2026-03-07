"""
GitHub MCP Server
Exposes tools for cloning Terraform files, modifying them, and opening PRs.

All write operations (PRs) are gated — no direct terraform apply ever runs.
"""
from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any

from github import Github, GithubException
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from config import cfg

app = Server("github-mcp")

def _gh_repo():
    g = Github(cfg.GITHUB_TOKEN)
    return g.get_repo(f"{cfg.GITHUB_REPO_OWNER}/{cfg.GITHUB_REPO_NAME}")


# ── Tool definitions ─────────────────────────────────────────────────────────
@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_terraform_file",
            description="Fetch the content of a Terraform (.tf) file from the repo.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to the .tf file in the repo"},
                    "branch": {"type": "string", "description": "Branch to read from (default: main)", "default": "main"},
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="list_terraform_files",
            description="List all .tf files in the repository.",
            inputSchema={
                "type": "object",
                "properties": {
                    "directory": {"type": "string", "description": "Sub-directory to search in (default: root)", "default": ""},
                },
            },
        ),
        Tool(
            name="create_remediation_pr",
            description=(
                "Create a GitHub Pull Request with a modified Terraform file "
                "that scales down or removes an underutilized resource."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string", "description": "AWS EC2 instance ID being remediated"},
                    "file_path": {"type": "string", "description": "Path to the .tf file to modify"},
                    "original_content": {"type": "string", "description": "Original file content"},
                    "modified_content": {"type": "string", "description": "Modified file content with fix applied"},
                    "justification": {"type": "string", "description": "Explanation of why this resource is flagged"},
                    "avg_cpu": {"type": "number", "description": "Average CPU % over lookback period"},
                    "monthly_cost": {"type": "number", "description": "Estimated monthly cost in USD"},
                    "langsmith_trace_url": {"type": "string", "description": "LangSmith trace URL for audit", "default": ""},
                },
                "required": ["instance_id", "file_path", "original_content", "modified_content", "justification"],
            },
        ),
    ]


# ── Tool implementations ─────────────────────────────────────────────────────
@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    if name == "get_terraform_file":
        return await _get_terraform_file(arguments)
    elif name == "list_terraform_files":
        return await _list_terraform_files(arguments)
    elif name == "create_remediation_pr":
        return await _create_remediation_pr(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _get_terraform_file(args: dict) -> list[TextContent]:
    file_path = args["file_path"]
    branch = args.get("branch", "main")

    try:
        repo = _gh_repo()
        content = repo.get_contents(file_path, ref=branch)
        decoded = base64.b64decode(content.content).decode("utf-8")
        result = {
            "file_path": file_path,
            "branch": branch,
            "sha": content.sha,
            "content": decoded,
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except GithubException as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _list_terraform_files(args: dict) -> list[TextContent]:
    directory = args.get("directory", "")

    try:
        repo = _gh_repo()
        tf_files = []

        def _recurse(path: str):
            contents = repo.get_contents(path)
            if not isinstance(contents, list):
                contents = [contents]
            for item in contents:
                if item.type == "dir":
                    _recurse(item.path)
                elif item.name.endswith(".tf"):
                    tf_files.append(item.path)

        _recurse(directory)
        return [TextContent(type="text", text=json.dumps({"terraform_files": tf_files}, indent=2))]
    except GithubException as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def _create_remediation_pr(args: dict) -> list[TextContent]:
    instance_id = args["instance_id"]
    file_path = args["file_path"]
    original_content = args["original_content"]
    modified_content = args["modified_content"]
    justification = args["justification"]
    avg_cpu = args.get("avg_cpu", 0.0)
    monthly_cost = args.get("monthly_cost", 0.0)
    trace_url = args.get("langsmith_trace_url", "")

    timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    branch_name = f"sre/remediate-{instance_id}-{timestamp}"

    try:
        repo = _gh_repo()

        # 0. Idempotency check — skip if an open PR already targets this instance
        open_prs = repo.get_pulls(state="open")
        for pr in open_prs:
            if instance_id in pr.title:
                result = {
                    "pr_number": pr.number,
                    "pr_url": pr.html_url,
                    "branch": pr.head.ref,
                    "instance_id": instance_id,
                    "status": "skipped",
                    "reason": f"Open PR #{pr.number} already exists for this instance.",
                }
                return [TextContent(type="text", text=json.dumps(result, indent=2))]

        # 1. Get default branch SHA
        default_branch = repo.default_branch
        source = repo.get_branch(default_branch)
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=source.commit.sha)

        # 2. Update the file on the new branch
        existing = repo.get_contents(file_path, ref=default_branch)
        repo.update_file(
            path=file_path,
            message=f"chore(sre): scale down underutilized instance {instance_id}",
            content=modified_content,
            sha=existing.sha,
            branch=branch_name,
        )

        # 3. Open Pull Request
        pr_body = f"""## Autonomous SRE Remediation — `{instance_id}`

### Finding Summary
| Metric | Value |
|---|---|
| **Instance ID** | `{instance_id}` |
| **Avg CPU (7d)** | `{avg_cpu:.1f}%` |
| **Estimated Monthly Cost** | `${monthly_cost:.2f}` |

### Justification
{justification}

### Changes
- File: `{file_path}`
- Action: Scale instance count to `0` (no direct `terraform apply` — human approval required)

### Audit Trail
- LangSmith Trace: {trace_url if trace_url else '_not available_'}

---
> **This PR was generated autonomously by the SRE FinOps Orchestrator.**
> No live infrastructure has been modified. An SRE engineer must review and merge this PR.
> The `terraform apply` must be executed manually after approval.
"""
        pr = repo.create_pull(
            title=f"[SRE-AUTO] Remediate underutilized instance {instance_id}",
            body=pr_body,
            head=branch_name,
            base=default_branch,
        )

        result = {
            "pr_number": pr.number,
            "pr_url": pr.html_url,
            "branch": branch_name,
            "instance_id": instance_id,
            "status": "created",
        }
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    except GithubException as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e), "status": "failed"}))]


# ── Entry point ───────────────────────────────────────────────────────────────
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
