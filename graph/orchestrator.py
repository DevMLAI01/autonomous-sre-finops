"""
LangGraph Orchestrator — Autonomous SRE & Cloud FinOps
Wires all 5 nodes into a stateful graph with HITL interrupt support.

Graph flow:
  START
    → investigate          (Node 1: find underutilized AWS resources)
    → rag_retrieve         (Node 2: check resource against internal docs)
    → decide               (Node 3: REMEDIATE | SKIP | DONE)
      ├─ REMEDIATE → remediate → hitl_gate → [loop or END]
      ├─ SKIP      → rag_retrieve (next resource)
      └─ DONE      → END
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from graph.state import OrchestratorState
from agents.investigator import investigate
from agents.rag_retriever import rag_retrieve
from agents.decision import decide, route_decision
from agents.remediator import remediate
from agents.hitl_gate import hitl_gate, route_after_hitl


def build_graph() -> StateGraph:
    """Construct and compile the LangGraph state machine."""
    builder = StateGraph(OrchestratorState)

    # ── Register nodes ────────────────────────────────────────────────────
    builder.add_node("investigate", investigate)
    builder.add_node("rag_retrieve", rag_retrieve)
    builder.add_node("decide", decide)
    builder.add_node("remediate", remediate)
    builder.add_node("hitl_gate", hitl_gate)

    # ── Edges ─────────────────────────────────────────────────────────────
    builder.add_edge(START, "investigate")
    builder.add_edge("investigate", "rag_retrieve")
    builder.add_edge("rag_retrieve", "decide")

    # Conditional routing from decision node
    builder.add_conditional_edges(
        "decide",
        route_decision,
        {
            "REMEDIATE": "remediate",
            "SKIP": "rag_retrieve",   # loop to next resource
            "DONE": END,
        },
    )

    builder.add_edge("remediate", "hitl_gate")

    # After HITL: use dedicated router (independent from decision node)
    builder.add_conditional_edges(
        "hitl_gate",
        route_after_hitl,
        {
            "SKIP": "rag_retrieve",  # more resources to process
            "DONE": END,
        },
    )

    return builder


def compile_graph(checkpointer=None):
    """Compile the graph. Pass an AsyncSqliteSaver instance from main for HITL persistence."""
    builder = build_graph()
    return builder.compile(checkpointer=checkpointer, interrupt_before=["hitl_gate"])


# ── Convenience runner ────────────────────────────────────────────────────────
async def run(thread_id: str = "default") -> dict:
    """
    Run the full workflow.
    Returns the final state after all resources are processed.

    For HITL resumption, call:
        graph.invoke({"human_approved": True}, config={"configurable": {"thread_id": thread_id}})
    """
    graph = compile_graph()
    config = {"configurable": {"thread_id": thread_id}}

    initial_state: OrchestratorState = {
        "flagged_resources": [],
        "investigation_summary": "",
        "resource_index": 0,
        "errors": [],
        "langsmith_trace_url": "",
        "notification_sent": False,
        "awaiting_approval": False,
        "human_approved": None,
    }

    final_state = await graph.ainvoke(initial_state, config=config)
    return final_state
