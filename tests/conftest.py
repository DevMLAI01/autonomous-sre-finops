"""Shared pytest fixtures for the Autonomous SRE FinOps Orchestrator test suite."""

import os

# Set all required env vars BEFORE any project imports.
# config.py reads GOOGLE_API_KEY at class-body level via os.environ[...],
# so these must be set before the config module is first imported.
os.environ.setdefault("GOOGLE_API_KEY", "test-google-api-key")
os.environ.setdefault("LANGCHAIN_API_KEY", "test-langchain-key")
os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
os.environ.setdefault("LANGCHAIN_PROJECT", "test-project")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "test-aws-key")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "test-aws-secret")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("GITHUB_TOKEN", "test-github-token")
os.environ.setdefault("GITHUB_REPO_OWNER", "test-owner")
os.environ.setdefault("GITHUB_REPO_NAME", "test-repo")
os.environ.setdefault("QDRANT_URL", "http://localhost:6333")
os.environ.setdefault("QDRANT_API_KEY", "test-qdrant-key")
os.environ.setdefault("QDRANT_COLLECTION", "sre_docs")
os.environ.setdefault("CPU_UTILIZATION_THRESHOLD", "5.0")
os.environ.setdefault("MONTHLY_COST_THRESHOLD", "100.0")
os.environ.setdefault("LOOKBACK_DAYS", "7")
os.environ.setdefault("SLACK_WEBHOOK_URL", "")
os.environ.setdefault("NOTIFICATION_EMAIL", "")

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def orphaned_resource():
    """An EC2 instance that is underutilized and has no active project."""
    return {
        "instance_id": "i-0abc123orphan",
        "instance_type": "t3.large",
        "avg_cpu_7d": 1.2,
        "average_cpu_percent": 1.2,
        "monthly_cost_usd": 145.0,
        "estimated_monthly_cost_usd": 145.0,
        "classification": "ORPHANED",
        "tags": {},
    }


@pytest.fixture
def protected_resource():
    """A production-tagged EC2 instance that must never be remediated."""
    return {
        "instance_id": "i-0def456prod",
        "instance_type": "m5.xlarge",
        "avg_cpu_7d": 72.0,
        "average_cpu_percent": 72.0,
        "monthly_cost_usd": 140.0,
        "estimated_monthly_cost_usd": 140.0,
        "classification": "PROTECTED",
        "tags": {"Environment": "production", "Name": "prod-api-server"},
    }


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client returning two fake document chunks."""
    mock = MagicMock()
    mock.search.return_value = [
        MagicMock(payload={"page_content": "This instance is not referenced by any active project."}, score=0.9),
        MagicMock(payload={"page_content": "No active projects reference this resource."}, score=0.85),
    ]
    return mock


@pytest.fixture
def mock_gemini_llm():
    """Mock Gemini LLM that returns an ORPHANED classification."""
    mock = MagicMock()
    mock.invoke.return_value = MagicMock(
        content='{"status": "ORPHANED", "confidence": 0.93, "reason": "CPU below threshold, no active project found"}'
    )
    return mock


@pytest.fixture
def mock_github_client():
    """Mock PyGithub client for PR creation assertions."""
    mock = MagicMock()
    mock_pr = MagicMock()
    mock_pr.number = 42
    mock_pr.html_url = "https://github.com/test-owner/test-repo/pull/42"
    mock_pr.head.ref = "sre/remediate-i-0abc123orphan-20260315"
    mock.create_pull.return_value = mock_pr
    mock.get_pulls.return_value = iter([])
    return mock


@pytest.fixture
def mock_aws_clients():
    """
    Mocked boto3 EC2 + CloudWatch with 4 sample instances:
      - i-0orphan001 / i-0orphan002: low CPU (~2%), high cost (m5.4xlarge ~$560/mo) -> flagged
      - i-0prod001: high CPU (72%), production tag -> skipped (CPU check fails)
      - i-0active001: high CPU (45%), t3.medium low cost -> skipped (CPU check fails)
    """
    ec2_mock = MagicMock()
    cloudwatch_mock = MagicMock()

    ec2_mock.describe_instances.return_value = {
        "Reservations": [
            {
                "Instances": [
                    {
                        "InstanceId": "i-0orphan001",
                        "InstanceType": "m5.4xlarge",
                        "State": {"Name": "running"},
                        "LaunchTime": MagicMock(isoformat=lambda: "2026-01-01T00:00:00+00:00"),
                        "Tags": [],
                    },
                    {
                        "InstanceId": "i-0orphan002",
                        "InstanceType": "m5.4xlarge",
                        "State": {"Name": "running"},
                        "LaunchTime": MagicMock(isoformat=lambda: "2026-01-01T00:00:00+00:00"),
                        "Tags": [],
                    },
                    {
                        "InstanceId": "i-0prod001",
                        "InstanceType": "c5.2xlarge",
                        "State": {"Name": "running"},
                        "LaunchTime": MagicMock(isoformat=lambda: "2026-01-01T00:00:00+00:00"),
                        "Tags": [{"Key": "Environment", "Value": "production"}],
                    },
                    {
                        "InstanceId": "i-0active001",
                        "InstanceType": "t3.medium",
                        "State": {"Name": "running"},
                        "LaunchTime": MagicMock(isoformat=lambda: "2026-01-01T00:00:00+00:00"),
                        "Tags": [],
                    },
                ]
            }
        ]
    }

    _cpu_map = {
        "i-0orphan001": 2.1,
        "i-0orphan002": 1.8,
        "i-0prod001": 72.0,
        "i-0active001": 45.0,
    }

    def _mock_get_metric_statistics(**kwargs):
        iid = kwargs["Dimensions"][0]["Value"]
        cpu = _cpu_map.get(iid, 50.0)
        return {"Datapoints": [{"Average": cpu}]}

    cloudwatch_mock.get_metric_statistics.side_effect = _mock_get_metric_statistics

    return {"ec2": ec2_mock, "cloudwatch": cloudwatch_mock}
