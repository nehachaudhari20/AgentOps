"""
Map observable event records to exactly one primary MFAV factor.

Never infers missing model/agent/tool identities from display names.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional, Sequence

from agenttrust.accountability.taxonomy import (
    DEFAULT_MAPPING_POLICY,
    MFAVFactor,
    MAPPING_POLICY_CATEGORY_PRIMARY_V1,
    SecondarySubtype,
    UNIDENTIFIED_ENTITY_KEY,
)
from agenttrust.schema.enums import EventCategory
from agenttrust.schema.event import EventRecord


@dataclass(frozen=True)
class Classification:
    """Exclusive primary-factor assignment for one event allocation."""

    event_id: str
    factor: MFAVFactor
    entity_id: str
    entity_kind: str
    unidentified: bool
    secondary_subtypes: tuple[str, ...] = ()
    policy: str = DEFAULT_MAPPING_POLICY
    rationale: str = ""
    warnings: tuple[str, ...] = ()


@dataclass
class ClassificationBatch:
    classifications: list[Classification] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _truthy_flag(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "y"}


def _memory_subtype_from_metadata(metadata: Mapping[str, str] | Sequence[tuple[str, str]]) -> bool:
    """Explicit memory evidence only — never from agent display names."""
    items = dict(metadata) if not isinstance(metadata, dict) else metadata
    subtype = items.get("subtype") or items.get("secondary_subtype")
    if subtype is not None and str(subtype).strip().lower() == SecondarySubtype.MEMORY.value:
        return True
    memory = items.get("memory")
    if memory is not None and _truthy_flag(str(memory)):
        return True
    return False


def _data_entity(event: EventRecord) -> tuple[str, str, bool]:
    """Prefer first output artifact, else first input; else unidentified."""
    if event.output_artifact_ids:
        return event.output_artifact_ids[0], "artifact", False
    if event.input_artifact_ids:
        return event.input_artifact_ids[0], "artifact", False
    return UNIDENTIFIED_ENTITY_KEY, "artifact", True


class EventFactorClassifier:
    """
    Deterministic exclusive classifier driven by a named mapping policy.

    Default policy ``category_primary_v1`` uses EventCategory as primary basis,
    with optional model_id / tool_id overrides where the policy permits.
    """

    def __init__(self, policy: str = DEFAULT_MAPPING_POLICY) -> None:
        if policy != MAPPING_POLICY_CATEGORY_PRIMARY_V1:
            raise ValueError(f"Unsupported MFAV mapping policy: {policy!r}")
        self.policy = policy

    def classify(self, event: EventRecord) -> Classification:
        return self._classify_category_primary_v1(event)

    def classify_many(self, events: Sequence[EventRecord]) -> ClassificationBatch:
        batch = ClassificationBatch()
        for ev in events:
            c = self.classify(ev)
            batch.classifications.append(c)
            batch.warnings.extend(c.warnings)
        return batch

    def _classify_category_primary_v1(self, event: EventRecord) -> Classification:
        warnings: list[str] = []
        meta = dict(event.metadata)
        memory_tag = _memory_subtype_from_metadata(meta)
        # Never treat agent_id / display-like names as memory evidence
        if event.agent_id and event.agent_id.strip().lower() == "memory" and not memory_tag:
            warnings.append(
                f"Event {event.event_id!r}: agent_id looks like 'Memory' but no explicit "
                "memory metadata; not applying memory subtype."
            )

        category = event.category
        secondary: tuple[str, ...] = ()

        if category == EventCategory.INSTRUCTION:
            return Classification(
                event_id=event.event_id,
                factor=MFAVFactor.PROMPT,
                entity_id=event.event_id,
                entity_kind="event",
                unidentified=False,
                secondary_subtypes=secondary,
                policy=self.policy,
                rationale="category=instruction → prompt",
                warnings=tuple(warnings),
            )

        if category == EventCategory.REASONING:
            if event.model_id:
                return Classification(
                    event_id=event.event_id,
                    factor=MFAVFactor.MODEL,
                    entity_id=event.model_id,
                    entity_kind="model",
                    unidentified=False,
                    secondary_subtypes=secondary,
                    policy=self.policy,
                    rationale="category=reasoning with explicit model_id → model",
                    warnings=tuple(warnings),
                )
            entity_id = event.agent_id if event.agent_id else UNIDENTIFIED_ENTITY_KEY
            unidentified = event.agent_id is None
            return Classification(
                event_id=event.event_id,
                factor=MFAVFactor.AGENT,
                entity_id=entity_id,
                entity_kind="agent",
                unidentified=unidentified,
                secondary_subtypes=secondary,
                policy=self.policy,
                rationale="category=reasoning without model_id → agent",
                warnings=tuple(warnings),
            )

        if category in (EventCategory.RETRIEVAL, EventCategory.KNOWLEDGE):
            entity_id, entity_kind, unidentified = _data_entity(event)
            if memory_tag:
                secondary = (SecondarySubtype.MEMORY.value,)
            return Classification(
                event_id=event.event_id,
                factor=MFAVFactor.DATA,
                entity_id=entity_id,
                entity_kind=entity_kind,
                unidentified=unidentified,
                secondary_subtypes=secondary,
                policy=self.policy,
                rationale=f"category={category.value} → data",
                warnings=tuple(warnings),
            )

        if category == EventCategory.TRANSFORMATION:
            if event.tool_id:
                return Classification(
                    event_id=event.event_id,
                    factor=MFAVFactor.TOOL,
                    entity_id=event.tool_id,
                    entity_kind="tool",
                    unidentified=False,
                    secondary_subtypes=secondary,
                    policy=self.policy,
                    rationale="category=transformation with explicit tool_id → tool",
                    warnings=tuple(warnings),
                )
            entity_id, entity_kind, unidentified = _data_entity(event)
            if memory_tag:
                secondary = (SecondarySubtype.MEMORY.value,)
            return Classification(
                event_id=event.event_id,
                factor=MFAVFactor.DATA,
                entity_id=entity_id,
                entity_kind=entity_kind,
                unidentified=unidentified,
                secondary_subtypes=secondary,
                policy=self.policy,
                rationale="category=transformation without tool_id → data",
                warnings=tuple(warnings),
            )

        if category == EventCategory.TOOL:
            if event.tool_id:
                entity_id, unidentified = event.tool_id, False
            else:
                # Tool invocation event id is observable; not fabricated
                entity_id, unidentified = event.event_id, False
            return Classification(
                event_id=event.event_id,
                factor=MFAVFactor.TOOL,
                entity_id=entity_id,
                entity_kind="tool",
                unidentified=unidentified,
                secondary_subtypes=secondary,
                policy=self.policy,
                rationale="category=tool → tool",
                warnings=tuple(warnings),
            )

        if category == EventCategory.DECISION:
            return Classification(
                event_id=event.event_id,
                factor=MFAVFactor.EXECUTION,
                entity_id=event.event_id,
                entity_kind="event",
                unidentified=False,
                secondary_subtypes=secondary,
                policy=self.policy,
                rationale="category=decision → execution",
                warnings=tuple(warnings),
            )

        # OTHER and any unexpected enum member
        if memory_tag:
            # Memory tag cannot promote OTHER into data; keep exclusive OTHER
            warnings.append(
                f"Event {event.event_id!r}: memory metadata present on OTHER category; "
                "primary factor remains other."
            )
        return Classification(
            event_id=event.event_id,
            factor=MFAVFactor.OTHER,
            entity_id=event.event_id,
            entity_kind="event",
            unidentified=False,
            secondary_subtypes=secondary,
            policy=self.policy,
            rationale=f"category={category.value} → other",
            warnings=tuple(warnings),
        )
