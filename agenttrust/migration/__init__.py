"""Legacy dataset migration into AgentTrust Phase 2.1 schema."""

from agenttrust.migration.legacy_events import migrate_legacy_events_file, migrate_legacy_records

__all__ = ["migrate_legacy_events_file", "migrate_legacy_records"]
