"""
Autonomous SRE & Cloud FinOps Orchestrator
Main entry point.

Usage:
    # Full run (will pause at HITL gate for human approval)
    python main.py

    # Resume after human approves (uses thread_id from previous run)
    python main.py --resume --thread-id <thread_id> --approved

    # Ingest docs into Qdrant first
    python -m rag.ingest --docs-dir ./docs

    # Run RAG quality gate
    python -m evaluation.ragas_eval
"""
from __future__ import annotations

import argparse
import asyncio
import uuid

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from graph.orchestrator import compile_graph

console = Console(highlight=False)


async def run_new(thread_id: str) -> None:
    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        await _run_new(thread_id, checkpointer)


async def _run_new(thread_id: str, checkpointer) -> None:
    graph = compile_graph(checkpointer)
    config = {"configurable": {"thread_id": thread_id}}

    initial_state = {
        "flagged_resources": [],
        "investigation_summary": "",
        "resource_index": 0,
        "errors": [],
        "langsmith_trace_url": "",
        "notification_sent": False,
        "awaiting_approval": False,
        "human_approved": None,
    }

    console.print(Panel(
        f"[bold cyan]Autonomous SRE & Cloud FinOps Orchestrator[/]\n"
        f"Thread ID: [yellow]{thread_id}[/]\n"
        f"Starting investigation...",
        title="SRE FinOps Orchestrator",
        border_style="cyan",
    ))

    async for event in graph.astream(initial_state, config=config):
        node = list(event.keys())[0]
        state = event[node]

        if node == "investigate":
            console.print(f"[green][OK] Investigate[/] - {state.get('investigation_summary', '')}")
        elif node == "rag_retrieve":
            r = state.get("current_resource", {})
            console.print(f"[green][OK] RAG Retrieve[/] - Assessed {r.get('instance_id', '')}")
        elif node == "decide":
            console.print(f"[yellow][>>] Decision[/] - {state.get('decision')} : {state.get('decision_reason', '')}")
        elif node == "remediate":
            pr = state.get("pr_result", {})
            console.print(f"[green][OK] Remediate[/] - PR created: {pr.get('pr_url', 'N/A')}")
        elif node == "__interrupt__":
            # state is a tuple of Interrupt objects; may be empty if interrupt_before fired
            payload = {}
            if state and hasattr(state[0], 'value') and isinstance(state[0].value, dict):
                payload = state[0].value
            console.print(Panel(
                f"[bold yellow]HITL GATE — Awaiting Human Approval[/]\n\n"
                f"{payload.get('message', 'Graph paused at HITL gate. Review the PR and resume.')}\n\n"
                f"[dim]Resume with:[/]\n"
                f"  python main.py --resume --thread-id {thread_id} --approved",
                title="Human-in-the-Loop",
                border_style="yellow",
            ))
            return  # Graph is paused — exit cleanly

    console.print(Panel("[bold green]Workflow complete.[/]", border_style="green"))


async def resume(thread_id: str, approved: bool) -> None:
    async with AsyncSqliteSaver.from_conn_string("checkpoints.db") as checkpointer:
        graph = compile_graph(checkpointer)
        config = {"configurable": {"thread_id": thread_id}}

        console.print(f"[cyan]Resuming thread {thread_id} with decision: {'APPROVED' if approved else 'REJECTED'}[/]")

        async for event in graph.astream(approved, config=config):
            node = list(event.keys())[0]
            state = event[node]
            console.print(f"[dim]{node}[/] -> {state.get('decision', '')}")

    console.print(Panel("[bold green]Workflow resumed and complete.[/]", border_style="green"))


def main():
    parser = argparse.ArgumentParser(description="Autonomous SRE & Cloud FinOps Orchestrator")
    parser.add_argument("--resume", action="store_true", help="Resume a paused workflow")
    parser.add_argument("--thread-id", type=str, default=None, help="Thread ID to resume")
    parser.add_argument("--approved", action="store_true", help="Human approval decision (True)")
    parser.add_argument("--rejected", action="store_true", help="Human rejection decision (False)")
    args = parser.parse_args()

    if args.resume:
        if not args.thread_id:
            print("ERROR: --thread-id is required for --resume")
            raise SystemExit(1)
        approved = not args.rejected  # default to approved unless --rejected
        asyncio.run(resume(args.thread_id, approved))
    else:
        thread_id = args.thread_id or str(uuid.uuid4())
        console.print(f"[dim]Thread ID: {thread_id}[/]  (save this for --resume)")
        asyncio.run(run_new(thread_id))


if __name__ == "__main__":
    main()
