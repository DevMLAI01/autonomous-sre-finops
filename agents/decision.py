"""
Node 3 — Decision Gate
Routes workflow based on RAG assessment: REMEDIATE, SKIP, or DONE.
"""
from __future__ import annotations

from graph.state import OrchestratorState


async def decide(state: OrchestratorState) -> OrchestratorState:
    """LangGraph node: route to remediation or skip based on RAG outcome."""
    errors = list(state.get("errors", []))

    try:
        assessment = state.get("rag_assessment", {})
        resource = state.get("current_resource", {})
        flagged = state.get("flagged_resources", [])
        idx = state.get("resource_index", 0)

        status = assessment.get("status", "PROTECTED")
        reason = assessment.get("reason", "No reason provided.")

        if status == "ORPHANED":
            decision = "REMEDIATE"
            print(f"[decision] {resource.get('instance_id')} -> REMEDIATE. Reason: {reason}")
        else:
            decision = "SKIP"
            print(f"[decision] {resource.get('instance_id')} -> SKIP (PROTECTED). Reason: {reason}")

        next_index = idx + 1
        if next_index >= len(flagged) and decision == "SKIP":
            decision = "DONE"

        return {
            **state,
            "decision": decision,
            "decision_reason": reason,
            "resource_index": next_index if decision == "SKIP" else idx,
            "errors": errors,
        }

    except Exception as e:
        msg = f"[decision] FAILED: {e}"
        print(msg)
        return {**state, "decision": "DONE", "errors": errors + [msg]}


def route_decision(state: OrchestratorState) -> str:
    """LangGraph conditional edge: maps decision to next node name."""
    return state.get("decision", "DONE")
