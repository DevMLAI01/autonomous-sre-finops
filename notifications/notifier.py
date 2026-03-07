"""
Notification module — Slack webhook + email mockup.
In production, replace the mock email with an SMTP/SES call.
"""
from __future__ import annotations

import json
import httpx
from config import cfg


SLACK_MESSAGE_TEMPLATE = """:rotating_light: *SRE FinOps Orchestrator — Approval Required*

*Instance:* `{instance_id}`
*Avg CPU (7d):* `{avg_cpu:.1f}%`
*Est. Monthly Cost:* `${monthly_cost:.2f}`

*Finding:* {reason}

*Pull Request:* <{pr_url}|PR #{pr_number}>
*LangSmith Trace:* {trace_url}

:white_check_mark: Merge the PR to approve remediation.
:x: Close/reject the PR to protect this resource.
"""


async def send_approval_request(
    instance_id: str,
    pr_url: str,
    pr_number: str,
    avg_cpu: float,
    monthly_cost: float,
    reason: str,
    trace_url: str,
) -> None:
    """Send Slack notification and log email mockup."""
    message = SLACK_MESSAGE_TEMPLATE.format(
        instance_id=instance_id,
        pr_url=pr_url,
        pr_number=pr_number,
        avg_cpu=avg_cpu,
        monthly_cost=monthly_cost,
        reason=reason,
        trace_url=trace_url if trace_url else "_not available_",
    )

    await _send_slack(message)
    _log_email_mockup(instance_id, pr_url, pr_number, avg_cpu, monthly_cost, reason, trace_url)


async def _send_slack(message: str) -> None:
    """POST to Slack incoming webhook. Silently skips if webhook not configured."""
    if not cfg.SLACK_WEBHOOK_URL:
        print("[notifier] SLACK_WEBHOOK_URL not set — skipping Slack notification")
        return

    payload = {"text": message}
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                cfg.SLACK_WEBHOOK_URL,
                content=json.dumps(payload),
                headers={"Content-Type": "application/json"},
                timeout=10.0,
            )
        if resp.status_code == 200:
            print("[notifier] Slack notification sent successfully")
        else:
            print(f"[notifier] Slack returned HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"[notifier] Slack send failed: {e}")


def _log_email_mockup(
    instance_id: str,
    pr_url: str,
    pr_number: str,
    avg_cpu: float,
    monthly_cost: float,
    reason: str,
    trace_url: str,
) -> None:
    """Mock email — logs to console. Replace with SMTP/SES in production."""
    email_body = f"""
TO: {cfg.NOTIFICATION_EMAIL}
SUBJECT: [ACTION REQUIRED] SRE FinOps — Approve PR #{pr_number} for {instance_id}

Dear SRE Team,

The Autonomous SRE FinOps Orchestrator has identified an underutilized resource
and created a Terraform Pull Request for your review.

  Instance ID  : {instance_id}
  Avg CPU (7d) : {avg_cpu:.1f}%
  Monthly Cost : ${monthly_cost:.2f}
  Finding      : {reason}

  Pull Request : {pr_url}
  Trace (APM)  : {trace_url if trace_url else 'N/A'}

ACTION REQUIRED:
  - Review the Terraform diff in the PR above
  - Merge to approve scale-down (no terraform apply is run automatically)
  - Close/reject the PR to protect this resource

This is an automated notification. No infrastructure has been modified yet.

Regards,
Autonomous SRE FinOps Orchestrator
""".strip()

    print("\n" + "=" * 60)
    print("[notifier] EMAIL MOCKUP (would send via SMTP/SES):")
    print("=" * 60)
    print(email_body)
    print("=" * 60 + "\n")
