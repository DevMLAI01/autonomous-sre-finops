# Autonomous SRE & Cloud FinOps Orchestrator

An enterprise-grade agentic AI system that autonomously detects underutilized AWS resources,
validates them against internal documentation via RAG, and raises Terraform IaC Pull Requests
for human-approved remediation — with zero direct infrastructure changes.

> **100% free-tier infrastructure.** Zero cloud spend beyond existing AWS resources.

---

## Architecture

```
+------------------------------------------------------------------+
|                    LangGraph State Machine                        |
|                                                                   |
|  START                                                            |
|    |                                                              |
|    v                                                              |
|  +-----------------+                                              |
|  |  Node 1         |  AWS MCP Server (read-only)                  |
|  |  Investigator   |<-- CloudWatch CPU + EC2 Describe             |
|  |                 |    Flags: CPU < 5%, Cost > $100/mo           |
|  +--------+--------+                                              |
|           |                                                       |
|    v                                                              |
|  +-----------------+                                              |
|  |  Node 2         |  Qdrant Serverless (vector search)           |
|  |  RAG Retriever  |<-- gemini-embedding-001 (3072 dims)          |
|  |                 |    "Is this resource protected?"             |
|  +--------+--------+                                              |
|           |                                                       |
|    v                                                              |
|  +-----------------+                                              |
|  |  Node 3         |                                              |
|  |  Decision Gate  |--PROTECTED--> log & loop/END                 |
|  |                 |--ORPHANED --> Node 4                         |
|  +--------+--------+                                              |
|           | ORPHANED                                              |
|    v                                                              |
|  +-----------------+                                              |
|  |  Node 4         |  GitHub MCP Server                           |
|  |  Remediator     |<-- Gemini patches .tf file (count = 0)       |
|  |                 |    Opens PR with full audit trail            |
|  +--------+--------+                                              |
|           |                                                       |
|    v                                                              |
|  +-----------------+  <-- INTERRUPT (graph pauses here)           |
|  |  Node 5         |                                              |
|  |  HITL Gate      |  Sends Slack + Email with PR link            |
|  |                 |  Awaits human approval to conclude           |
|  +--------+--------+                                              |
|           |                                                       |
|          END                                                      |
+------------------------------------------------------------------+
```

**Key design principle:** No `terraform apply` ever runs autonomously. All remediation goes
through a GitHub PR requiring explicit human review and merge.

---

## Tech Stack

| Layer | Tool | Free Tier |
|---|---|---|
| Orchestration | LangGraph + SQLite checkpointing | Yes |
| LLM | `gemini-2.5-flash-lite` (Google AI Studio) | 1000 req/day |
| Embeddings | `gemini-embedding-001` (3072 dims) | Yes |
| RAG Vector DB | Qdrant Serverless | 1 GB |
| Observability | LangSmith | 5000 traces/month |
| RAG Evaluation | Ragas 0.4.3 | Open source |
| AWS Access | Boto3 via MCP (read-only IAM) | IAM-controlled |
| IaC | Terraform via GitHub PRs | GitHub free |
| Tool Access | Model Context Protocol (MCP) | Open source |

**Total monthly cost: $0** (all free tiers)

---

## Project Structure

```
autonomous-sre-finops/
├── agents/
│   ├── llm_client.py          # Gemini LLM + embeddings + LangSmith tracing
│   ├── investigator.py        # Node 1: AWS anomaly detection via MCP
│   ├── rag_retriever.py       # Node 2: Qdrant RAG assessment
│   ├── decision.py            # Node 3: REMEDIATE / SKIP / DONE routing
│   ├── remediator.py          # Node 4: Terraform patch + GitHub PR via MCP
│   └── hitl_gate.py           # Node 5: LangGraph interrupt + notification
├── mcp_servers/
│   ├── aws_mcp_server.py      # Read-only EC2 + CloudWatch (stdio MCP)
│   └── github_mcp_server.py   # PR creation with idempotency guard (stdio MCP)
├── graph/
│   ├── state.py               # OrchestratorState TypedDict
│   └── orchestrator.py        # Graph assembly + AsyncSqliteSaver checkpoint
├── rag/
│   ├── ingest.py              # Embed + upsert docs into Qdrant
│   └── retriever.py           # RAG query + Gemini assessment
├── evaluation/
│   └── ragas_eval.py          # CI/CD quality gate (Faithfulness + AnswerRelevancy >= 0.85)
├── notifications/
│   └── notifier.py            # Slack webhook + email notification
├── docs/
│   ├── sample_architecture.md # Architecture documentation
│   ├── resource_registry.md   # Protected resource registry
│   └── project_status.md      # Active/decommissioned projects
├── terraform_templates/
│   └── scale_down.tf.jinja    # Jinja2 template for Terraform patches
├── tests/
├── main.py                    # CLI entry point
├── config.py                  # Centralised env var config
├── requirements.txt
└── .env.example
```

---

## Setup

### Prerequisites

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) package manager

### 1. Install dependencies

```bash
uv pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Fill in your API keys
```

Required credentials:

| Variable | Where to get it |
|---|---|
| `GOOGLE_API_KEY` | [Google AI Studio](https://aistudio.google.com) (free) |
| `LANGCHAIN_API_KEY` | [LangSmith](https://smith.langchain.com) (free dev tier) |
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Read-only IAM user (see policy below) |
| `AWS_DEFAULT_REGION` | Your EC2 region (e.g. `ap-south-1`) |
| `GITHUB_TOKEN` | GitHub PAT with `repo` scope |
| `GITHUB_REPO_OWNER` / `GITHUB_REPO_NAME` | Terraform repo to open PRs against |
| `QDRANT_URL` / `QDRANT_API_KEY` | [Qdrant Cloud](https://cloud.qdrant.io) (free tier) |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook (optional) |

### 3. Ingest internal docs into Qdrant

```bash
uv run python -m rag.ingest --docs-dir ./docs
```

This embeds your architecture docs, resource registry, and project status files into the
vector store so the RAG retriever can assess whether a flagged resource is protected.

### 4. Run the RAG quality gate

```bash
uv run python -m evaluation.ragas_eval
```

Must score >= 0.85 on Faithfulness and Answer Relevancy before deploying to production.

### 5. Run the orchestrator

```bash
uv run python main.py
```

The workflow pauses at the HITL gate and prints a `thread_id`. The graph state is
persisted to `checkpoints.db` (SQLite) so it survives process restarts.

### 6. Resume after human review

```bash
# Approve the PR and trigger terraform apply planning:
uv run python main.py --resume --thread-id <thread_id> --approved

# Reject (resource stays as-is):
uv run python main.py --resume --thread-id <thread_id> --rejected
```

---

## How it works — step by step

1. **Investigate**: The Investigator agent queries AWS via a read-only MCP server.
   It flags EC2 instances with average CPU < 5% over 7 days and estimated cost > $100/month.

2. **RAG Retrieve**: For each flagged instance, the RAG Retriever embeds the resource
   metadata and searches Qdrant for relevant internal docs (architecture decisions,
   resource registry, active projects). A Gemini LLM then classifies the resource as
   `PROTECTED` or `ORPHANED` with a confidence score and justification.

3. **Decision**: `ORPHANED` resources proceed to remediation. `PROTECTED` resources are
   skipped and logged. When all resources are processed, the graph terminates.

4. **Remediate**: For `ORPHANED` resources, the Remediator:
   - Asks Gemini to identify the relevant `.tf` file in the GitHub repo
   - Asks Gemini to modify the file (sets `count = 0` on the instance resource)
   - Creates a GitHub PR with full audit trail (CPU%, cost, RAG justification, LangSmith trace)
   - Includes idempotency guard: skips if a PR for this instance already exists

5. **HITL Gate**: The graph **interrupts** (pauses execution). A notification is sent to
   Slack/email with the PR link. The SRE engineer reviews the PR and resumes the graph
   with `--approved` or `--rejected`. No infrastructure is modified until the PR is
   manually merged and `terraform apply` is run by a human.

---

## Security & Guardrails

| Guardrail | Implementation |
|---|---|
| No direct execution | `terraform apply` is strictly prohibited; all changes via GitHub PRs |
| Least privilege | AWS credentials are read-only (EC2 Describe + CloudWatch only) |
| Conservative RAG | Resource defaults to `PROTECTED` if LLM cannot parse context |
| PR idempotency | Skips PR creation if an open PR already exists for the instance |
| RAG quality gate | Ragas Faithfulness + AnswerRelevancy >= 0.85 required |
| HITL mandatory | No change proceeds without explicit human approval via `--approved` |
| State persistence | SQLite checkpointing — graph survives crashes, supports HITL resume |
| Audit trail | Every PR includes LangSmith trace URL, CPU%, cost, RAG justification |

---

## AWS IAM Policy (Read-Only)

The AWS credentials only need these permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudwatch:GetMetricStatistics",
        "ec2:DescribeInstances"
      ],
      "Resource": "*"
    }
  ]
}
```

> Cost Explorer (`ce:GetCostAndUsage`) is **not required**. Monthly cost is estimated
> from on-demand pricing based on instance type — no additional IAM permissions needed.

---

## Thresholds (configurable in `.env`)

| Variable | Default | Description |
|---|---|---|
| `CPU_UTILIZATION_THRESHOLD` | `5.0` | Flag instances with avg CPU below this % |
| `MONTHLY_COST_THRESHOLD` | `100.0` | Only flag if estimated cost exceeds this USD/mo |
| `LOOKBACK_DAYS` | `7` | CloudWatch lookback window for CPU averages |
| `RAGAS_MIN_FAITHFULNESS` | `0.85` | Minimum RAG faithfulness score for CI gate |
| `RAGAS_MIN_ANSWER_RELEVANCY` | `0.85` | Minimum RAG answer relevancy for CI gate |

---

## LangSmith Observability

Every LLM call is traced to LangSmith automatically via `LANGCHAIN_TRACING_V2=true`.
Each remediation PR includes the LangSmith trace URL for full audit trail.

Set `LANGCHAIN_PROJECT` in `.env` to organise traces by project.

---

## License

This project is intended **for educational and demonstration purposes only**.

- You may use, study, and modify this code for personal learning and non-commercial projects.
- Do not deploy this system against production AWS infrastructure without thorough security review.
- The author provides no warranties and accepts no liability for any damages arising from use of this code.
- Third-party services used (Google Gemini, Qdrant, LangSmith, GitHub, AWS) are subject to their own terms of service.
