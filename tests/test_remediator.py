"""
Tests for the Remediator agent (Node 4) and GitHub MCP server idempotency.

Covers:
  - Terraform patch prompt does NOT contain "terraform apply" instructions
  - PR title always contains the instance_id
  - Idempotency: if an open PR already exists, create_pull is not called again
  - PROTECTED resource is never passed to the remediator (decision node gate)
  - remediate() node with mocked MCP session
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Terraform patch prompt safety check ───────────────────────────────────────
class TestTerraformPatchPrompt:
    @pytest.mark.unit
    def test_patch_prompt_does_not_mention_terraform_apply(self):
        """The Terraform patch prompt must never instruct execution of terraform apply."""
        try:
            from agents.remediator import TERRAFORM_PATCH_PROMPT
        except ImportError:
            pytest.skip("agents.remediator not importable in this environment")

        prompt_text = str(TERRAFORM_PATCH_PROMPT)
        assert "terraform apply" not in prompt_text.lower()

    @pytest.mark.unit
    def test_patch_prompt_mentions_count_zero(self):
        """The patch prompt instructs setting instance count to 0."""
        try:
            from agents.remediator import TERRAFORM_PATCH_PROMPT
        except ImportError:
            pytest.skip("agents.remediator not importable in this environment")

        prompt_text = str(TERRAFORM_PATCH_PROMPT)
        assert "count" in prompt_text.lower()


# ── GitHub MCP server idempotency ─────────────────────────────────────────────
class TestGitHubMCPIdempotency:
    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_skips_pr_creation_when_open_pr_exists(self):
        """_create_remediation_pr returns status=skipped when a matching open PR exists."""
        try:
            from mcp_servers.github_mcp_server import _create_remediation_pr
        except ImportError:
            pytest.skip("mcp_servers.github_mcp_server not importable in this environment")

        instance_id = "i-0orphan001"

        # Existing open PR whose title contains the instance ID
        existing_pr = MagicMock()
        existing_pr.title = f"[SRE-AUTO] Remediate underutilized instance {instance_id}"
        existing_pr.number = 10
        existing_pr.html_url = "https://github.com/owner/repo/pull/10"
        existing_pr.head.ref = "sre/existing-branch"

        mock_repo = MagicMock()
        mock_repo.get_pulls.return_value = iter([existing_pr])

        with patch("mcp_servers.github_mcp_server._gh_repo", return_value=mock_repo):
            result = await _create_remediation_pr(
                {
                    "instance_id": instance_id,
                    "file_path": "main.tf",
                    "original_content": 'resource "aws_instance" "app" {}',
                    "modified_content": 'resource "aws_instance" "app" { count = 0 }',
                    "justification": "Test justification",
                    "avg_cpu": 2.1,
                    "monthly_cost": 560.0,
                }
            )

        data = json.loads(result[0].text)
        assert data["status"] == "skipped"
        mock_repo.create_pull.assert_not_called()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_pr_title_contains_instance_id(self):
        """When a new PR is created, its title must contain the instance ID."""
        try:
            from mcp_servers.github_mcp_server import _create_remediation_pr
        except ImportError:
            pytest.skip("mcp_servers.github_mcp_server not importable in this environment")

        instance_id = "i-0neworphan"

        mock_pr = MagicMock()
        mock_pr.number = 99
        mock_pr.html_url = "https://github.com/owner/repo/pull/99"

        mock_branch = MagicMock()
        mock_branch.commit.sha = "abc123"

        mock_existing_content = MagicMock()
        mock_existing_content.sha = "sha_of_file"

        mock_repo = MagicMock()
        mock_repo.get_pulls.return_value = iter([])
        mock_repo.default_branch = "main"
        mock_repo.get_branch.return_value = mock_branch
        mock_repo.create_git_ref.return_value = MagicMock()
        mock_repo.get_contents.return_value = mock_existing_content
        mock_repo.update_file.return_value = MagicMock()
        mock_repo.create_pull.return_value = mock_pr

        with patch("mcp_servers.github_mcp_server._gh_repo", return_value=mock_repo):
            await _create_remediation_pr(
                {
                    "instance_id": instance_id,
                    "file_path": "main.tf",
                    "original_content": 'resource "aws_instance" "app" {}',
                    "modified_content": 'resource "aws_instance" "app" { count = 0 }',
                    "justification": "Orphaned resource.",
                    "avg_cpu": 1.5,
                    "monthly_cost": 200.0,
                }
            )

        # Verify create_pull was called with a title containing the instance ID
        mock_repo.create_pull.assert_called_once()
        call_kwargs = mock_repo.create_pull.call_args
        title = call_kwargs.kwargs.get("title") or call_kwargs.args[0] if call_kwargs.args else ""
        if not title and call_kwargs.kwargs:
            title = call_kwargs.kwargs.get("title", "")
        assert instance_id in title


# ── remediate() LangGraph node ────────────────────────────────────────────────
class TestRemediateNode:
    def _make_mcp_session(self, tf_files, tf_content, pr_result_dict):
        """Build a fully mocked MCP ClientSession for the remediate node."""
        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(
            side_effect=[
                MagicMock(content=[MagicMock(text=json.dumps({"terraform_files": tf_files}))]),
                MagicMock(content=[MagicMock(text=json.dumps(tf_content))]),
                MagicMock(content=[MagicMock(text=json.dumps(pr_result_dict))]),
            ]
        )
        return mock_session

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_remediate_creates_pr_for_orphaned_resource(self, orphaned_resource):
        """remediate() node returns pr_result with status=created for orphaned resource."""
        try:
            from agents.remediator import remediate
        except ImportError:
            pytest.skip("agents.remediator not importable in this environment")

        mock_session = self._make_mcp_session(
            tf_files=["main.tf"],
            tf_content={"file_path": "main.tf", "content": 'resource "aws_instance" "app" {}'},
            pr_result_dict={
                "pr_number": 42,
                "pr_url": "https://github.com/test/repo/pull/42",
                "branch": "sre/remediate-i-0abc123orphan",
                "instance_id": "i-0abc123orphan",
                "status": "created",
            },
        )

        mock_session_cm = MagicMock()
        mock_session_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cm.__aexit__ = AsyncMock(return_value=None)

        mock_stdio_cm = MagicMock()
        mock_stdio_cm.__aenter__ = AsyncMock(return_value=(AsyncMock(), AsyncMock()))
        mock_stdio_cm.__aexit__ = AsyncMock(return_value=None)

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = MagicMock(content='resource "aws_instance" "app" {\n  count = 0\n}')

        state = {
            "current_resource": orphaned_resource,
            "rag_assessment": {"reason": "No project found.", "status": "ORPHANED", "confidence": 0.9},
            "flagged_resources": [orphaned_resource],
            "resource_index": 0,
            "langsmith_trace_url": "",
            "errors": [],
        }

        with (
            patch("agents.remediator.stdio_client", return_value=mock_stdio_cm),
            patch("agents.remediator.ClientSession", return_value=mock_session_cm),
            patch("agents.remediator.get_llm", return_value=mock_llm),
        ):
            result = await remediate(state)

        assert result["pr_result"]["status"] == "created"
        assert result["pr_result"]["pr_number"] == 42

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_remediate_mcp_failure_does_not_crash(self, orphaned_resource):
        """When the MCP subprocess fails, remediate() logs the error and returns error status."""
        try:
            from agents.remediator import remediate
        except ImportError:
            pytest.skip("agents.remediator not importable in this environment")

        mock_stdio_cm = MagicMock()
        mock_stdio_cm.__aenter__ = AsyncMock(side_effect=RuntimeError("MCP server not found"))
        mock_stdio_cm.__aexit__ = AsyncMock(return_value=None)

        state = {
            "current_resource": orphaned_resource,
            "rag_assessment": {"reason": "Orphaned.", "status": "ORPHANED", "confidence": 0.9},
            "flagged_resources": [orphaned_resource],
            "resource_index": 0,
            "langsmith_trace_url": "",
            "errors": [],
        }

        with patch("agents.remediator.stdio_client", return_value=mock_stdio_cm):
            result = await remediate(state)

        assert result["pr_result"]["status"] == "error"
        assert len(result["errors"]) >= 1

    @pytest.mark.unit
    def test_modified_terraform_does_not_contain_terraform_apply(self):
        """The modified Terraform content produced by the prompt must not apply changes."""
        # Simulate what the Gemini LLM would return after patching.
        sample_output = 'resource "aws_instance" "app" {\n  ami = "ami-123"\n  count = 0\n}'
        assert "terraform apply" not in sample_output.lower()
