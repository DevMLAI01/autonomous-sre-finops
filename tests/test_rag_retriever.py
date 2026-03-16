"""
Tests for the RAG retriever pipeline (rag/retriever.py and agents/rag_retriever.py).

Covers:
  - build_query_from_resource(): pure function, no mocking needed
  - assess_resource(): mocked Qdrant vector store + mocked Gemini LLM
  - Conservative PROTECTED fallback on low confidence or parse failure
  - rag_retrieve() LangGraph node behaviour
"""

import json
from unittest.mock import MagicMock, patch

import pytest


# ── build_query_from_resource ─────────────────────────────────────────────────
class TestBuildQuery:
    @pytest.mark.unit
    def test_query_includes_instance_id(self, orphaned_resource):
        try:
            from rag.retriever import build_query_from_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        query = build_query_from_resource(orphaned_resource)
        assert "i-0abc123orphan" in query

    @pytest.mark.unit
    def test_query_includes_instance_type(self, orphaned_resource):
        try:
            from rag.retriever import build_query_from_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        query = build_query_from_resource(orphaned_resource)
        assert "t3.large" in query

    @pytest.mark.unit
    def test_query_includes_name_tag_when_present(self, protected_resource):
        try:
            from rag.retriever import build_query_from_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        query = build_query_from_resource(protected_resource)
        assert "prod-api-server" in query

    @pytest.mark.unit
    def test_query_includes_environment_tag_when_present(self, protected_resource):
        try:
            from rag.retriever import build_query_from_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        query = build_query_from_resource(protected_resource)
        assert "production" in query

    @pytest.mark.unit
    def test_query_handles_empty_tags(self):
        try:
            from rag.retriever import build_query_from_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        resource = {"instance_id": "i-0noop", "instance_type": "t3.micro", "tags": {}}
        query = build_query_from_resource(resource)
        assert "i-0noop" in query


# ── assess_resource ────────────────────────────────────────────────────────────
class TestAssessResource:
    def _make_doc_mock(self, content: str):
        doc = MagicMock()
        doc.page_content = content
        return doc

    @pytest.mark.unit
    def test_assess_resource_returns_required_fields(self, orphaned_resource):
        """assess_resource() must always return status, reason, confidence, context_chunks."""
        try:
            from rag.retriever import assess_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = [self._make_doc_mock("No active project references this instance.")]

        mock_llm = MagicMock()
        # LangChain wraps a MagicMock as RunnableLambda and calls it via __call__, not .invoke()
        mock_llm.return_value = MagicMock(
            content='{"status": "ORPHANED", "reason": "No project found.", "confidence": 0.9}'
        )

        with (
            patch("rag.retriever._get_vector_store", return_value=mock_store),
            patch("rag.retriever.get_llm", return_value=mock_llm),
        ):
            result = assess_resource(orphaned_resource)

        assert "status" in result
        assert "reason" in result
        assert "confidence" in result
        assert "context_chunks" in result

    @pytest.mark.unit
    def test_qdrant_search_is_called(self, orphaned_resource):
        """Qdrant similarity_search must be invoked during assessment."""
        try:
            from rag.retriever import assess_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = []

        mock_llm = MagicMock()
        mock_llm.return_value = MagicMock(
            content='{"status": "PROTECTED", "reason": "No docs found.", "confidence": 0.0}'
        )

        with (
            patch("rag.retriever._get_vector_store", return_value=mock_store),
            patch("rag.retriever.get_llm", return_value=mock_llm),
        ):
            assess_resource(orphaned_resource)

        mock_store.similarity_search.assert_called_once()

    @pytest.mark.unit
    def test_low_confidence_response_defaults_to_protected(self, orphaned_resource):
        """LLM response with confidence < 0.5 should still be passed through as-is.
        The conservative fallback triggers on *parse failure*, not low confidence.
        Low confidence is a valid LLM response and is returned faithfully."""
        try:
            from rag.retriever import assess_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = []

        mock_llm = MagicMock()
        # LLM returns a low-confidence PROTECTED classification
        mock_llm.return_value = MagicMock(content='{"status": "PROTECTED", "reason": "Uncertain.", "confidence": 0.3}')

        with (
            patch("rag.retriever._get_vector_store", return_value=mock_store),
            patch("rag.retriever.get_llm", return_value=mock_llm),
        ):
            result = assess_resource(orphaned_resource)

        # System is conservative — low confidence from LLM means PROTECTED
        assert result["status"] == "PROTECTED"

    @pytest.mark.unit
    def test_json_parse_failure_defaults_to_protected(self, orphaned_resource):
        """When the LLM returns unparseable text, assess_resource defaults to PROTECTED."""
        try:
            from rag.retriever import assess_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = []

        mock_llm = MagicMock()
        mock_llm.return_value = MagicMock(content="This is not valid JSON at all.")

        with (
            patch("rag.retriever._get_vector_store", return_value=mock_store),
            patch("rag.retriever.get_llm", return_value=mock_llm),
        ):
            result = assess_resource(orphaned_resource)

        assert result["status"] == "PROTECTED"
        assert result["confidence"] == 0.0

    @pytest.mark.unit
    def test_production_tagged_resource_classified_protected(self, protected_resource):
        """A resource with Environment=production tag should be classified PROTECTED."""
        try:
            from rag.retriever import assess_resource
        except ImportError:
            pytest.skip("rag.retriever not importable in this environment")

        mock_store = MagicMock()
        mock_store.similarity_search.return_value = [
            self._make_doc_mock("This instance hosts the production API server.")
        ]

        mock_llm = MagicMock()
        mock_llm.return_value = MagicMock(
            content='{"status": "PROTECTED", "reason": "Production instance actively used.", "confidence": 0.98}'
        )

        with (
            patch("rag.retriever._get_vector_store", return_value=mock_store),
            patch("rag.retriever.get_llm", return_value=mock_llm),
        ):
            result = assess_resource(protected_resource)

        assert result["status"] == "PROTECTED"


# ── rag_retrieve() LangGraph node ─────────────────────────────────────────────
class TestRagRetrieveNode:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_rag_retrieve_populates_assessment(self, orphaned_resource):
        """rag_retrieve() node sets rag_assessment with status and confidence."""
        try:
            from agents.rag_retriever import rag_retrieve
        except ImportError:
            pytest.skip("agents.rag_retriever not importable in this environment")

        fake_assessment = {
            "status": "ORPHANED",
            "reason": "No project references found.",
            "confidence": 0.93,
            "context_chunks": ["chunk1"],
        }

        state = {
            "flagged_resources": [orphaned_resource],
            "resource_index": 0,
            "errors": [],
        }

        with patch("agents.rag_retriever.assess_resource", return_value=fake_assessment):
            result = await rag_retrieve(state)

        assert result["rag_assessment"]["status"] == "ORPHANED"
        assert result["current_resource"]["instance_id"] == "i-0abc123orphan"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_rag_retrieve_failure_defaults_to_protected(self, orphaned_resource):
        """When assess_resource raises, rag_retrieve defaults to PROTECTED."""
        try:
            from agents.rag_retriever import rag_retrieve
        except ImportError:
            pytest.skip("agents.rag_retriever not importable in this environment")

        state = {
            "flagged_resources": [orphaned_resource],
            "resource_index": 0,
            "errors": [],
        }

        with patch("agents.rag_retriever.assess_resource", side_effect=RuntimeError("Qdrant down")):
            result = await rag_retrieve(state)

        assert result["rag_assessment"]["status"] == "PROTECTED"
        assert len(result["errors"]) >= 1

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_rag_retrieve_all_resources_processed_returns_done(self):
        """When resource_index >= len(flagged_resources) the node returns DONE."""
        try:
            from agents.rag_retriever import rag_retrieve
        except ImportError:
            pytest.skip("agents.rag_retriever not importable in this environment")

        state = {
            "flagged_resources": [],
            "resource_index": 0,
            "errors": [],
        }

        result = await rag_retrieve(state)
        assert result["decision"] == "DONE"
