# Resource Registry — Active & Protected AWS Resources

## EC2 Instance Inventory

### i-prod-web-01 / web-frontend-prod
- **Status**: ACTIVE — do not decommission
- **Project**: customer-portal
- **Environment**: production
- **Team**: frontend
- **Purpose**: Serves the customer-facing web portal. High traffic during business hours.
- **Tags**: Name=web-frontend-prod, Project=customer-portal, Environment=production

### i-dr-standby-01 / disaster-recovery-standby
- **Status**: PROTECTED — disaster recovery asset
- **Project**: platform-reliability
- **Environment**: dr-standby
- **Team**: sre
- **Purpose**: Hot standby for the production database tier. Must remain running at all times per SLA.
- **Tags**: Name=disaster-recovery-standby, Project=platform-reliability, Environment=dr-standby

### i-loadtest-01 / load-test-standby
- **Status**: PROTECTED until 2026-06-01
- **Project**: q4-performance-testing
- **Environment**: staging
- **Team**: platform
- **Purpose**: Pre-warmed EC2 instance reserved for Q4 load testing. Must NOT be decommissioned.
  The performance engineering team requires this instance to be online and pre-warmed
  to simulate sudden traffic spikes for the Q4 load test campaign.
- **Protected Until**: 2026-06-01
- **Tags**: Name=load-test-standby, Project=q4-performance-testing, ProtectedUntil=2026-06-01

### i-batch-legacy-01 / legacy-batch-processor
- **Status**: ORPHANED — safe to decommission
- **Project**: data-migration-2022
- **Environment**: production (legacy)
- **Team**: data-engineering (disbanded)
- **Purpose**: Used for a one-time data migration from legacy Oracle DB to Redshift in 2022.
  Migration completed December 2022. Instance was never cleaned up.
  The data-migration-2022 project is CLOSED. No active workloads depend on this instance.
- **Action**: Safe to scale down and eventually terminate.
- **Tags**: Name=legacy-batch-processor, Project=data-migration-2022, Environment=production

### i-dev-sandbox-backend-01 / old-dev-sandbox
- **Status**: REVIEW REQUIRED — likely orphaned
- **Project**: unknown / untagged
- **Environment**: development
- **Team**: backend
- **Purpose**: Created as a scratch environment by a backend engineer who left the company in 2023.
  No project documentation references this sandbox. No active PRs or deployments use it.
  The backend team confirmed they have a newer sandbox (i-dev-sandbox-backend-02) and do not
  need this instance.
- **Action**: Safe to decommission. Confirm with backend team lead before terminating.
- **Tags**: Name=old-dev-sandbox, Project=unknown, Environment=development, Team=backend

## Protection Rules

1. Any instance tagged `Environment=dr-standby` is PROTECTED and must never be modified.
2. Any instance tagged `ProtectedUntil` with a future date is PROTECTED until that date.
3. Instances in CLOSED projects (status: COMPLETE or CLOSED) are ORPHANED.
4. Instances with `Project=unknown` or no project tag require team confirmation before action.
5. Production instances need SRE lead approval even if flagged as orphaned.
