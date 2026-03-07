"""
Node 2 — RAG Retriever Agent
Cross-references flagged resources against internal docs in Qdrant.
"""
from __future__ import annotations

from graph.state import OrchestratorState
from rag.retriever import assess_resource


async def rag_retrieve(state: OrchestratorState) -> OrchestratorState:
    """LangGraph node: retrieve RAG context and assess the current resource."""
    flagged = state.get("flagged_resources", [])
    idx = state.get("resource_index", 0)
    errors = list(state.get("errors", []))

    if idx >= len(flagged):
        return {**state, "decision": "DONE", "decision_reason": "All resources processed."}

    resource = flagged[idx]
    print(f"[rag_retriever] Assessing resource {resource['instance_id']} ({idx + 1}/{len(flagged)})...")

    try:
        assessment = assess_resource(resource)
        print(
            f"[rag_retriever] Assessment: {assessment['status']} "
            f"(confidence={assessment['confidence']:.2f}) — {assessment['reason']}"
        )
        return {
            **state,
            "current_resource": resource,
            "rag_assessment": assessment,
            "errors": errors,
        }

    except Exception as e:
        msg = f"[rag_retriever] FAILED for {resource.get('instance_id')}: {e}"
        print(msg)
        # Default to PROTECTED on RAG failure — safe conservative fallback
        safe_assessment = {
            "status": "PROTECTED",
            "reason": f"RAG retrieval failed ({e}) — defaulting to PROTECTED for safety.",
            "confidence": 0.0,
            "context_chunks": [],
        }
        return {
            **state,
            "current_resource": resource,
            "rag_assessment": safe_assessment,
            "errors": errors + [msg],
        }
