# Project Status Registry

## Active Projects

### customer-portal
- **Status**: ACTIVE
- **Team**: frontend, backend
- **Cloud Resources**: EC2 instances tagged Project=customer-portal are in active use.
- **SLA**: 99.9% uptime required. No modifications without change management approval.

### platform-reliability
- **Status**: ACTIVE (ongoing)
- **Team**: SRE
- **Cloud Resources**: Includes disaster recovery standbys. All DR resources are permanently protected.
- **Note**: This project owns all instances tagged `Environment=dr-standby`.

### q4-performance-testing
- **Status**: ACTIVE — in pre-test preparation phase
- **Team**: Platform Engineering
- **Cloud Resources**: Staging instances reserved for load testing. Do not decommission.
- **Timeline**: Testing window opens 2026-05-01, concludes 2026-06-01.
- **Key Instance**: load-test-standby (i-loadtest-01) — pre-warmed, must remain running.

## Completed / Closed Projects

### data-migration-2022
- **Status**: COMPLETE — closed December 2022
- **Team**: Data Engineering (team disbanded)
- **Cloud Resources**: All instances tagged `Project=data-migration-2022` are ORPHANED.
  The migration from Oracle to Amazon Redshift was completed successfully.
  No active processes depend on these resources. All instances are safe to decommission.
- **Estimated savings**: ~$145/month per legacy batch processor instance.

### alpha-experiments-2021
- **Status**: COMPLETE — closed March 2021
- **Cloud Resources**: Any instance tagged `Project=alpha-experiments-2021` is orphaned.
  The experiment concluded. All data was archived to S3.

## SRE Policies

### Cost Optimization Policy
- Resources with < 5% average CPU over 7 days AND cost > $100/month are flagged for review.
- Flagged resources are cross-referenced against this registry before any action.
- All remediation actions require a GitHub PR and human approval — no automated `terraform apply`.

### Decommission Workflow
1. Automated detection via FinOps Orchestrator
2. RAG cross-reference against this registry
3. GitHub PR created (count = 0 in Terraform)
4. SRE team reviews and approves or rejects PR
5. Manual `terraform apply` by SRE after approval
