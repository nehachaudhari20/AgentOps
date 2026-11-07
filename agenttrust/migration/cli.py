"""Non-destructive legacy migration entry point."""

from __future__ import annotations

from pathlib import Path

from agenttrust.migration.legacy_events import migrate_legacy_events_file


def main() -> None:
    repo = Path(__file__).resolve().parents[2]
    source = repo / "data" / "raw_events" / "events.json"
    output = repo / "data" / "processed_events"
    payload = migrate_legacy_events_file(source, output)
    report = payload["migration_report"]
    print(f"Migrated {report['migrated_event_count']} events, {report['migrated_artifact_count']} artifacts.")
    print(f"Wrote: {payload['output_paths']}")


if __name__ == "__main__":
    main()
