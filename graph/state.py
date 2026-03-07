"""
LangGraph shared state schema for the SRE FinOps Orchestrator.
All nodes read from and write to this TypedDict.
"""
from __future__ import annotations

from typing import Any, Literal, Optional
from typing_extensions import TypedDict


class OrchestratorState(TypedDict, total=False):
    # ── Node 1: Investigator output ──────────────────────────────────────
    flagged_resources: list[dict]          # list of underutilized resources found
    investigation_summary: str             # human-readable summary

    # ── Node 2: RAG Retriever output ─────────────────────────────────────
    current_resource: dict                 # resource being processed in this cycle
    rag_assessment: dict                   # {status, reason, confidence, context_chunks}

    # ── Node 3: Decision output ───────────────────────────────────────────
    decision: Literal["REMEDIATE", "SKIP", "DONE"]
    decision_reason: str

    # ── Node 4: Remediator output ─────────────────────────────────────────
    modified_terraform: str               # modified .tf file content
    pr_result: dict                       # {pr_url, pr_number, branch, status}

    # ── Node 5: HITL Gate ─────────────────────────────────────────────────
    notification_sent: bool
    awaiting_approval: bool
    human_approved: Optional[bool]        # None = pending, True/False = decided

    # ── Cross-cutting ─────────────────────────────────────────────────────
    resource_index: int                   # which resource we're currently processing
    langsmith_trace_url: str
    errors: list[str]
