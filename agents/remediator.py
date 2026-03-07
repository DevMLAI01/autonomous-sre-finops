"""
Node 4 — Remediator Agent
Uses Gemini to modify Terraform files and creates a GitHub PR via MCP.
"""
from __future__ import annotations

import json
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_core.prompts import ChatPromptTemplate

from agents.llm_client import get_llm
from graph.state import OrchestratorState
from config import cfg


TERRAFORM_PATCH_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a Terraform expert. Given a .tf file and a target EC2 instance ID,
modify the Terraform configuration to set the instance count to 0 (scale it down).
If there is no explicit count, add `count = 0` to the resource block.
Return ONLY the complete modified .tf file content, no explanation.""",
    ),
    (
        "human",
        """Target instance ID: {instance_id}
Original Terraform file ({file_path}):
```hcl
{original_content}
```
Return the full modified file:""",
    ),
])


_TF_FILE_SELECTOR_PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        "You are a Terraform expert. Given a list of .tf file paths, pick the ONE file most "
        "likely to define an EC2 instance with the given ID. Consider naming conventions: "
        "files named 'ec2', 'instances', 'compute', or 'main' are strong candidates. "
        "Reply with ONLY the exact file path, nothing else.",
    ),
    (
        "human",
        "Instance ID: {instance_id}\n\nAvailable .tf files:\n{file_list}\n\nBest matching file:",
    ),
])


async def _find_tf_file_for_instance(session: ClientSession, instance_id: str) -> tuple[str, str]:
    """
    List TF files, ask Gemini which one most likely defines this instance,
    then fetch and return (file_path, original_content).
    """
    files_result = await session.call_tool("list_terraform_files", arguments={})
    tf_files = json.loads(files_result.content[0].text).get("terraform_files", [])

    if not tf_files:
        raise RuntimeError("No Terraform files found in repository.")

    # Use Gemini to pick the best-matching file (falls back to first if LLM fails)
    target_file = tf_files[0]
    if len(tf_files) > 1:
        try:
            llm = get_llm(temperature=0.0)
            chain = _TF_FILE_SELECTOR_PROMPT | llm
            response = chain.invoke({
                "instance_id": instance_id,
                "file_list": "\n".join(tf_files),
            })
            candidate = response.content.strip().strip("`\"'")
            if candidate in tf_files:
                target_file = candidate
                print(f"[remediator] Gemini selected TF file: {target_file}")
            else:
                print(f"[remediator] Gemini returned unknown file '{candidate}', falling back to {target_file}")
        except Exception as e:
            print(f"[remediator] TF file selection failed ({e}), using fallback: {target_file}")

    file_result = await session.call_tool("get_terraform_file", arguments={"file_path": target_file})
    file_data = json.loads(file_result.content[0].text)
    return file_data["file_path"], file_data["content"]


async def remediate(state: OrchestratorState) -> OrchestratorState:
    """LangGraph node: generate Terraform patch and open GitHub PR."""
    resource = state.get("current_resource", {})
    assessment = state.get("rag_assessment", {})
    instance_id = resource.get("instance_id", "")
    avg_cpu = resource.get("average_cpu_percent", 0.0)
    monthly_cost = resource.get("estimated_monthly_cost_usd", 0.0)
    trace_url = state.get("langsmith_trace_url", "")
    errors = list(state.get("errors", []))

    print(f"[remediator] Generating remediation PR for {instance_id}...")

    try:
        server_params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mcp_servers.github_mcp_server"],
        )

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # 1. Find the relevant TF file
                file_path, original_content = await _find_tf_file_for_instance(session, instance_id)

                # 2. Use Gemini to patch the Terraform file
                llm = get_llm(temperature=0.0)
                chain = TERRAFORM_PATCH_PROMPT | llm
                patch_response = chain.invoke({
                    "instance_id": instance_id,
                    "file_path": file_path,
                    "original_content": original_content,
                })
                modified_content = patch_response.content.strip()
                # Strip markdown code fences if LLM wrapped the output
                if modified_content.startswith("```"):
                    lines = modified_content.split("\n")
                    modified_content = "\n".join(lines[1:-1])

                # 3. Open GitHub PR via MCP
                pr_result_raw = await session.call_tool(
                    "create_remediation_pr",
                    arguments={
                        "instance_id": instance_id,
                        "file_path": file_path,
                        "original_content": original_content,
                        "modified_content": modified_content,
                        "justification": assessment.get("reason", "Resource identified as orphaned."),
                        "avg_cpu": avg_cpu,
                        "monthly_cost": monthly_cost,
                        "langsmith_trace_url": trace_url,
                    },
                )
                pr_result = json.loads(pr_result_raw.content[0].text)

        if pr_result.get("status") == "skipped":
            print(f"[remediator] PR already exists for {instance_id}: {pr_result.get('pr_url')}")
        else:
            print(f"[remediator] PR created: {pr_result.get('pr_url', 'N/A')}")

        return {
            **state,
            "modified_terraform": modified_content,
            "pr_result": pr_result,
            "errors": errors,
        }

    except Exception as e:
        msg = f"[remediator] FAILED for {instance_id}: {e}"
        print(msg)
        # Advance to HITL anyway with an error-flagged PR result so operator is notified
        flagged = state.get("flagged_resources", [])
        idx = state.get("resource_index", 0)
        return {
            **state,
            "modified_terraform": "",
            "pr_result": {"status": "error", "error": str(e), "instance_id": instance_id},
            "decision": "DONE" if idx + 1 >= len(flagged) else "SKIP",
            "resource_index": idx + 1,
            "errors": errors + [msg],
        }
