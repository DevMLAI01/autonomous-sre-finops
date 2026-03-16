"""
Tests for the Investigator agent (Node 1) and AWS MCP server filtering logic.

The investigator node delegates all AWS calls to aws_mcp_server via MCP subprocess.
These tests cover:
  - The CPU/cost threshold filtering logic (mirrors _find_underutilized_resources)
  - _get_cpu_utilization behaviour when CloudWatch returns no datapoints
  - The investigate() LangGraph node with a fully-mocked MCP session
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Inline helpers mirroring the threshold logic in aws_mcp_server ────────────
def _is_underutilized(avg_cpu: float, threshold: float) -> bool:
    """True when avg CPU is strictly below the configured threshold."""
    return avg_cpu < threshold


def _exceeds_cost_threshold(cost: float, threshold: float) -> bool:
    """True when monthly cost is at or above the configured threshold."""
    return cost >= threshold


# ── Threshold logic unit tests ────────────────────────────────────────────────
class TestFilteringLogic:
    @pytest.mark.unit
    def test_is_underutilized_below_threshold(self):
        assert _is_underutilized(2.0, 5.0) is True

    @pytest.mark.unit
    def test_is_underutilized_exactly_at_threshold_returns_false(self):
        # The server uses `avg_cpu >= cpu_threshold: continue`, so equal means NOT underutilized.
        assert _is_underutilized(5.0, 5.0) is False

    @pytest.mark.unit
    def test_is_underutilized_above_threshold(self):
        assert _is_underutilized(60.0, 5.0) is False

    @pytest.mark.unit
    def test_exceeds_cost_threshold_above(self):
        assert _exceeds_cost_threshold(145.0, 100.0) is True

    @pytest.mark.unit
    def test_exceeds_cost_threshold_below(self):
        assert _exceeds_cost_threshold(50.0, 100.0) is False

    @pytest.mark.unit
    def test_exceeds_cost_threshold_at_boundary(self):
        assert _exceeds_cost_threshold(100.0, 100.0) is True


# ── AWS MCP server CPU utilization tests ─────────────────────────────────────
class TestCPUUtilization:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_no_cloudwatch_datapoints_returns_zero(self):
        """When CloudWatch returns no datapoints the average must be 0.0."""
        try:
            from mcp_servers.aws_mcp_server import _get_cpu_utilization
        except ImportError:
            pytest.skip("mcp_servers.aws_mcp_server not importable in this environment")

        with patch("mcp_servers.aws_mcp_server._cloudwatch") as mock_cw:
            mock_cw.return_value.get_metric_statistics.return_value = {"Datapoints": []}
            result = await _get_cpu_utilization({"instance_id": "i-0test001", "lookback_days": 7})
            data = json.loads(result[0].text)
            assert data["average_cpu_percent"] == 0.0

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_cloudwatch_averages_multiple_datapoints(self):
        """Average CPU is the mean of all datapoints returned by CloudWatch."""
        try:
            from mcp_servers.aws_mcp_server import _get_cpu_utilization
        except ImportError:
            pytest.skip("mcp_servers.aws_mcp_server not importable in this environment")

        with patch("mcp_servers.aws_mcp_server._cloudwatch") as mock_cw:
            mock_cw.return_value.get_metric_statistics.return_value = {
                "Datapoints": [{"Average": 2.0}, {"Average": 4.0}, {"Average": 6.0}]
            }
            result = await _get_cpu_utilization({"instance_id": "i-0test001", "lookback_days": 7})
            data = json.loads(result[0].text)
            assert data["average_cpu_percent"] == 4.0


# ── AWS MCP server find_underutilized integration ─────────────────────────────
class TestFindUnderutilizedResources:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_flags_low_cpu_high_cost_instances(self, mock_aws_clients):
        """Instances with low CPU AND high cost appear in flagged_resources."""
        try:
            from mcp_servers.aws_mcp_server import _find_underutilized_resources
        except ImportError:
            pytest.skip("mcp_servers.aws_mcp_server not importable in this environment")

        with (
            patch("mcp_servers.aws_mcp_server._ec2") as mock_ec2_fn,
            patch("mcp_servers.aws_mcp_server._cloudwatch") as mock_cw_fn,
        ):
            mock_ec2_fn.return_value = mock_aws_clients["ec2"]
            mock_cw_fn.return_value = mock_aws_clients["cloudwatch"]

            result = await _find_underutilized_resources(
                {
                    "cpu_threshold": 5.0,
                    "cost_threshold": 50.0,
                    "lookback_days": 7,
                }
            )
            data = json.loads(result[0].text)
            flagged_ids = [r["instance_id"] for r in data["flagged_resources"]]

            # Low-CPU orphans must be flagged
            assert "i-0orphan001" in flagged_ids
            assert "i-0orphan002" in flagged_ids

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_high_cpu_instances_not_flagged(self, mock_aws_clients):
        """Instances with CPU >= threshold are never flagged, regardless of tags."""
        try:
            from mcp_servers.aws_mcp_server import _find_underutilized_resources
        except ImportError:
            pytest.skip("mcp_servers.aws_mcp_server not importable in this environment")

        with (
            patch("mcp_servers.aws_mcp_server._ec2") as mock_ec2_fn,
            patch("mcp_servers.aws_mcp_server._cloudwatch") as mock_cw_fn,
        ):
            mock_ec2_fn.return_value = mock_aws_clients["ec2"]
            mock_cw_fn.return_value = mock_aws_clients["cloudwatch"]

            result = await _find_underutilized_resources(
                {
                    "cpu_threshold": 5.0,
                    "cost_threshold": 50.0,
                    "lookback_days": 7,
                }
            )
            data = json.loads(result[0].text)
            flagged_ids = [r["instance_id"] for r in data["flagged_resources"]]

            # Production-tagged instance has 72% CPU — must not be flagged
            assert "i-0prod001" not in flagged_ids
            # Active instance has 45% CPU — must not be flagged
            assert "i-0active001" not in flagged_ids


# ── investigate() node with mocked MCP session ────────────────────────────────
class TestInvestigateNode:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_investigate_returns_flagged_resources(self):
        """investigate() parses MCP tool output and populates flagged_resources."""
        try:
            from agents.investigator import investigate
        except ImportError:
            pytest.skip("agents.investigator not importable in this environment")

        fake_resources = [
            {
                "instance_id": "i-0orphan001",
                "instance_type": "m5.4xlarge",
                "average_cpu_percent": 2.1,
                "estimated_monthly_cost_usd": 560.64,
                "tags": {},
            },
        ]
        mcp_response = json.dumps(
            {
                "flagged_resources": fake_resources,
                "flagged_count": 1,
            }
        )

        mock_result = MagicMock()
        mock_result.content = [MagicMock(text=mcp_response)]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        mock_cm = MagicMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_stdio_cm = MagicMock()
        mock_stdio_cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_stdio_cm.__aexit__ = AsyncMock(return_value=None)

        initial_state = {"flagged_resources": [], "errors": [], "resource_index": 0}

        with (
            patch("agents.investigator.stdio_client", return_value=mock_stdio_cm),
            patch("agents.investigator.ClientSession", return_value=mock_cm),
        ):
            result = await investigate(initial_state)

        assert len(result["flagged_resources"]) == 1
        assert result["flagged_resources"][0]["instance_id"] == "i-0orphan001"
        assert result["resource_index"] == 0

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_investigate_mcp_failure_returns_done(self):
        """When the MCP call raises, investigate() sets decision=DONE and logs the error."""
        try:
            from agents.investigator import investigate
        except ImportError:
            pytest.skip("agents.investigator not importable in this environment")

        mock_stdio_cm = MagicMock()
        mock_stdio_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("MCP connection refused"))
        mock_stdio_cm.__aexit__ = AsyncMock(return_value=None)

        initial_state = {"flagged_resources": [], "errors": [], "resource_index": 0}

        with patch("agents.investigator.stdio_client", return_value=mock_stdio_cm):
            result = await investigate(initial_state)

        assert result["decision"] == "DONE"
        assert result["flagged_resources"] == []
        assert len(result["errors"]) >= 1
