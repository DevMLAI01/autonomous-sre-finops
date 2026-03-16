"""
Tests for the HITL Gate agent (Node 5).

Covers:
  - route_after_hitl() routing logic
  - hitl_gate() skips interrupt when remediator reported an error
  - hitl_gate() calls interrupt() and returns approved state on resume
  - Notification does not crash when SLACK_WEBHOOK_URL is empty
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── route_after_hitl ──────────────────────────────────────────────────────────
class TestRouteAfterHitl:
    @pytest.mark.unit
    def test_routes_to_skip_when_more_resources(self):
        try:
            from agents.hitl_gate import route_after_hitl
        except ImportError:
            pytest.skip("agents.hitl_gate not importable in this environment")

        state = {"decision": "SKIP", "human_approved": True}
        assert route_after_hitl(state) == "SKIP"

    @pytest.mark.unit
    def test_routes_to_done_when_all_processed(self):
        try:
            from agents.hitl_gate import route_after_hitl
        except ImportError:
            pytest.skip("agents.hitl_gate not importable in this environment")

        state = {"decision": "DONE", "human_approved": True}
        assert route_after_hitl(state) == "DONE"

    @pytest.mark.unit
    def test_routes_to_done_when_rejected(self):
        try:
            from agents.hitl_gate import route_after_hitl
        except ImportError:
            pytest.skip("agents.hitl_gate not importable in this environment")

        state = {"decision": "DONE", "human_approved": False}
        assert route_after_hitl(state) == "DONE"

    @pytest.mark.unit
    def test_defaults_to_done_when_decision_missing(self):
        try:
            from agents.hitl_gate import route_after_hitl
        except ImportError:
            pytest.skip("agents.hitl_gate not importable in this environment")

        state = {}
        assert route_after_hitl(state) == "DONE"


# ── hitl_gate() node ──────────────────────────────────────────────────────────
class TestHitlGateNode:
    def _base_state(self, pr_status="created"):
        return {
            "current_resource": {
                "instance_id": "i-0abc123orphan",
                "average_cpu_percent": 1.2,
                "estimated_monthly_cost_usd": 145.0,
            },
            "pr_result": {
                "status": pr_status,
                "pr_url": "https://github.com/owner/repo/pull/42",
                "pr_number": 42,
            },
            "rag_assessment": {"reason": "No project found.", "confidence": 0.93},
            "langsmith_trace_url": "",
            "flagged_resources": [{"instance_id": "i-0abc123orphan"}],
            "resource_index": 0,
            "errors": [],
        }

    @pytest.mark.asyncio
    @pytest.mark.hitl
    async def test_hitl_gate_skips_interrupt_on_remediator_error(self):
        """When pr_result.status == 'error', hitl_gate must NOT call interrupt()."""
        try:
            from agents.hitl_gate import hitl_gate
        except ImportError:
            pytest.skip("agents.hitl_gate not importable in this environment")

        state = self._base_state(pr_status="error")
        state["pr_result"]["error"] = "MCP server failed"

        with patch("langgraph.types.interrupt") as mock_interrupt:
            result = await hitl_gate(state)

        mock_interrupt.assert_not_called()
        assert result["awaiting_approval"] is False

    @pytest.mark.asyncio
    @pytest.mark.hitl
    async def test_hitl_gate_calls_interrupt_for_valid_pr(self):
        """For a valid PR (status != 'error'), hitl_gate must call interrupt()."""
        try:
            from agents.hitl_gate import hitl_gate
        except ImportError:
            pytest.skip("agents.hitl_gate not importable in this environment")

        state = self._base_state(pr_status="created")

        with (
            patch("langgraph.types.interrupt", return_value=True) as mock_interrupt,
            patch("agents.hitl_gate.send_approval_request", new_callable=AsyncMock),
        ):
            result = await hitl_gate(state)

        mock_interrupt.assert_called_once()
        assert result["human_approved"] is True

    @pytest.mark.asyncio
    @pytest.mark.hitl
    async def test_hitl_gate_approved_true_sets_human_approved(self):
        """When interrupt() returns True, human_approved must be True in the result state."""
        try:
            from agents.hitl_gate import hitl_gate
        except ImportError:
            pytest.skip("agents.hitl_gate not importable in this environment")

        state = self._base_state(pr_status="created")

        with (
            patch("langgraph.types.interrupt", return_value=True),
            patch("agents.hitl_gate.send_approval_request", new_callable=AsyncMock),
        ):
            result = await hitl_gate(state)

        assert result["human_approved"] is True
        assert result["awaiting_approval"] is False

    @pytest.mark.asyncio
    @pytest.mark.hitl
    async def test_hitl_gate_rejected_sets_human_approved_false(self):
        """When interrupt() returns False, human_approved must be False."""
        try:
            from agents.hitl_gate import hitl_gate
        except ImportError:
            pytest.skip("agents.hitl_gate not importable in this environment")

        state = self._base_state(pr_status="created")

        with (
            patch("langgraph.types.interrupt", return_value=False),
            patch("agents.hitl_gate.send_approval_request", new_callable=AsyncMock),
        ):
            result = await hitl_gate(state)

        assert result["human_approved"] is False

    @pytest.mark.asyncio
    @pytest.mark.hitl
    async def test_notification_does_not_crash_when_slack_empty(self):
        """hitl_gate must succeed even when send_approval_request raises (non-fatal)."""
        try:
            from agents.hitl_gate import hitl_gate
        except ImportError:
            pytest.skip("agents.hitl_gate not importable in this environment")

        state = self._base_state(pr_status="created")

        with (
            patch("langgraph.types.interrupt", return_value=True),
            patch(
                "agents.hitl_gate.send_approval_request",
                new_callable=AsyncMock,
                side_effect=Exception("Slack webhook not configured"),
            ),
        ):
            result = await hitl_gate(state)

        # Node must complete despite notification failure
        assert result["human_approved"] is True
        assert any("Notification failed" in e for e in result.get("errors", []))


# ── Notifier unit tests ────────────────────────────────────────────────────────
class TestNotifier:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_send_approval_request_no_crash_with_empty_slack_url(self):
        """send_approval_request completes silently when SLACK_WEBHOOK_URL is empty."""
        try:
            from notifications.notifier import send_approval_request
        except ImportError:
            pytest.skip("notifications.notifier not importable in this environment")

        import os

        original = os.environ.get("SLACK_WEBHOOK_URL", "")
        os.environ["SLACK_WEBHOOK_URL"] = ""

        try:
            # Should not raise
            await send_approval_request(
                instance_id="i-0test",
                pr_url="https://github.com/owner/repo/pull/1",
                pr_number="1",
                avg_cpu=1.5,
                monthly_cost=145.0,
                reason="Test",
                trace_url="",
            )
        finally:
            os.environ["SLACK_WEBHOOK_URL"] = original
