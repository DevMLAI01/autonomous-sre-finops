# Internal Architecture & Resource Registry

## Active Projects

### Q4 Performance Testing (q4-performance-testing)
- **Status**: Active
- **Team**: Platform Engineering
- **Resources**: Instances tagged `Project: q4-performance-testing` are reserved for load testing.
- **Protected Until**: 2026-06-01
- **Note**: The standby instance `load-test-standby` (i-test002) must NOT be decommissioned.
  It is pre-warmed and ready for sudden load spikes.

### Data Migration 2022 (data-migration-2022)
- **Status**: COMPLETE — project closed December 2022
- **Resources**: All instances tagged `Project: data-migration-2022` are orphaned.
  They were used during a one-time data migration and were not cleaned up.
- **Action**: Safe to decommission.

## Disaster Recovery Standbys
- Instances tagged `Environment: dr-standby` are protected and must never be scaled to 0.
- Contact the on-call SRE before modifying any DR instance.

## Development Sandboxes
- Instances tagged `Environment: development` with no active project tag are considered
  ephemeral. Review with the owning team before decommissioning.
- The backend team maintains a shared dev sandbox. Confirm with the team before removal.

## Cost Thresholds
- Resources costing > $100/month with < 5% CPU over 7 days are flagged for review.
- Resources in `production` environment require SRE lead approval before any changes.
