"""
Node 5 — Human-in-the-Loop (HITL) Gate
Pauses execution, sends notification with PR link + LangSmith trace,
and waits for an explicit human approval signal before concluding.
"""
from __future__ import annotations

from graph.state import OrchestratorState
from notifications.notifier import send_approval_request


async def hitl_gate(state: OrchestratorState) -> OrchestratorState:
    """
    LangGraph node with interrupt.
    LangGraph's interrupt() mechanism pauses the graph here.
    Execution resumes when the human calls graph.invoke() with human_approved=True/False.
    """
    from langgraph.types import interrupt

    errors = list(state.get("errors", []))
    resource = state.get("current_resource", {})
    pr_result = state.get("pr_result", {})
    assessment = state.get("rag_assessment", {})
    trace_url = state.get("langsmith_trace_url", "")

    instance_id = resource.get("instance_id", "unknown")
    pr_url = pr_result.get("pr_url", "N/A")
    pr_number = pr_result.get("pr_number", "N/A")
    avg_cpu = resource.get("average_cpu_percent", 0.0)
    monthly_cost = resource.get("estimated_monthly_cost_usd", 0.0)
    reason = assessment.get("reason", "")

    # If remediator errored, skip HITL and move on
    if pr_result.get("status") == "error":
        print(f"[hitl_gate] Skipping HITL — remediator reported an error for {instance_id}")
        flagged = state.get("flagged_resources", [])
        idx = state.get("resource_index", 0)
        return {
            **state,
            "notification_sent": False,
            "awaiting_approval": False,
            "human_approved": None,
            "decision": "DONE" if idx >= len(flagged) else "SKIP",
            "errors": errors,
        }

    print(f"[hitl_gate] Sending approval request for PR #{pr_number} ({instance_id})...")

    try:
        await send_approval_request(
            instance_id=instance_id,
            pr_url=pr_url,
            pr_number=str(pr_number),
            avg_cpu=avg_cpu,
            monthly_cost=monthly_cost,
            reason=reason,
            trace_url=trace_url,
        )
    except Exception as e:
        msg = f"[hitl_gate] Notification failed (non-fatal): {e}"
        print(msg)
        errors = errors + [msg]

    # ── INTERRUPT: pause graph execution until human resumes ──────────────
    human_decision = interrupt({
        "type": "approval_request",
        "instance_id": instance_id,
        "pr_url": pr_url,
        "pr_number": pr_number,
        "message": (
            f"SRE FinOps Orchestrator flagged instance {instance_id} "
            f"(CPU={avg_cpu:.1f}%, cost=${monthly_cost:.2f}/mo).\n"
            f"PR: {pr_url}\n"
            f"Approve remediation? Reply with True/False."
        ),
    })

    approved = bool(human_decision)
    print(f"[hitl_gate] Human decision received: {'APPROVED' if approved else 'REJECTED'}")

    flagged = state.get("flagged_resources", [])
    idx = state.get("resource_index", 0)
    next_index = idx + 1

    return {
        **state,
        "notification_sent": True,
        "awaiting_approval": False,
        "human_approved": approved,
        "resource_index": next_index,
        "decision": "DONE" if next_index >= len(flagged) else "SKIP",
        "errors": errors,
    }


def route_after_hitl(state: OrchestratorState) -> str:
    """Dedicated HITL router — independent from the decision node router."""
    return state.get("decision", "DONE")
