"""
Tests for the LangGraph orchestrator (graph/orchestrator.py).

Covers:
  - build_graph() constructs a StateGraph with all expected nodes
  - compile_graph(None) compiles without error
  - The graph exposes the correct node names
"""

from unittest.mock import MagicMock, patch

import pytest


EXPECTED_NODES = {"investigate", "rag_retrieve", "decide", "remediate", "hitl_gate"}


class TestBuildGraph:
    @pytest.mark.unit
    def test_build_graph_returns_state_graph(self):
        """build_graph() must return a StateGraph instance."""
        try:
            from graph.orchestrator import build_graph
            from langgraph.graph import StateGraph
        except ImportError:
            pytest.skip("graph.orchestrator or langgraph not importable")

        with patch("agents.llm_client.ChatGoogleGenerativeAI"), patch("agents.llm_client.GoogleGenerativeAIEmbeddings"):
            builder = build_graph()

        assert isinstance(builder, StateGraph)

    @pytest.mark.unit
    def test_graph_has_all_expected_nodes(self):
        """All five orchestrator nodes must be registered in the graph."""
        try:
            from graph.orchestrator import build_graph
        except ImportError:
            pytest.skip("graph.orchestrator not importable")

        with patch("agents.llm_client.ChatGoogleGenerativeAI"), patch("agents.llm_client.GoogleGenerativeAIEmbeddings"):
            builder = build_graph()

        # StateGraph stores nodes in builder.nodes (a dict keyed by node name)
        node_names = set(builder.nodes.keys())
        for expected in EXPECTED_NODES:
            assert expected in node_names, f"Missing expected node: '{expected}'"

    @pytest.mark.unit
    def test_compile_graph_succeeds_without_checkpointer(self):
        """compile_graph(None) must compile to a runnable graph without errors."""
        try:
            from graph.orchestrator import compile_graph
        except ImportError:
            pytest.skip("graph.orchestrator not importable")

        with patch("agents.llm_client.ChatGoogleGenerativeAI"), patch("agents.llm_client.GoogleGenerativeAIEmbeddings"):
            graph = compile_graph(checkpointer=None)

        assert graph is not None

    @pytest.mark.unit
    def test_compiled_graph_has_ainvoke(self):
        """Compiled graph must expose ainvoke (async execution interface)."""
        try:
            from graph.orchestrator import compile_graph
        except ImportError:
            pytest.skip("graph.orchestrator not importable")

        with patch("agents.llm_client.ChatGoogleGenerativeAI"), patch("agents.llm_client.GoogleGenerativeAIEmbeddings"):
            graph = compile_graph(checkpointer=None)

        assert hasattr(graph, "ainvoke"), "Compiled graph must have ainvoke method"
        assert hasattr(graph, "astream"), "Compiled graph must have astream method"


class TestOrchestratorState:
    @pytest.mark.unit
    def test_orchestrator_state_has_required_keys(self):
        """OrchestratorState TypedDict must expose all documented state keys."""
        try:
            from graph.state import OrchestratorState
        except ImportError:
            pytest.skip("graph.state not importable")

        annotations = OrchestratorState.__annotations__
        required_keys = [
            "flagged_resources",
            "current_resource",
            "rag_assessment",
            "decision",
            "pr_result",
            "human_approved",
            "resource_index",
            "errors",
        ]
        for key in required_keys:
            assert key in annotations, f"OrchestratorState missing key: '{key}'"
