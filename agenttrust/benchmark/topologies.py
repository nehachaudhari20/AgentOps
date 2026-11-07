"""
Explicit workflow topology constructors.

Each topology has documented construction rules and meaningful execution
semantics — not arbitrary random DAGs labeled as realistic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Sequence

from agenttrust.benchmark.manifest import TopologyId
from agenttrust.benchmark.scenarios import ScenarioTemplate


class StepKind(str, Enum):
    PROMPT = "prompt"
    REASONING = "reasoning"
    RETRIEVAL = "retrieval"
    DOCUMENT = "document"
    EMBEDDING = "embedding"
    TOOL = "tool_call"
    ACTION = "action"
    INVOKE = "invoke"  # recorded as reasoning/tool with invokes_event_ids


@dataclass
class PlannedStep:
    """One observable event to materialize."""

    local_id: str
    kind: StepKind
    agent_index: int
    dep_local_ids: tuple[str, ...] = ()
    invoke_local_ids: tuple[str, ...] = ()
    retry_of: str | None = None
    produce_artifact: bool = True
    consume_from: tuple[str, ...] = ()  # local ids whose artifacts are inputs
    tool_name: str | None = None
    use_model: bool = False
    memory_tag: bool = False
    is_outcome: bool = False


@dataclass
class WorkflowBlueprint:
    topology_id: TopologyId
    steps: list[PlannedStep] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _pick_agent(agents: Sequence[str], preferred_roles: Sequence[str], fallback: int = 0) -> int:
    for i, a in enumerate(agents):
        base = a.split("-")[0]
        if base in preferred_roles:
            return i
    return min(fallback, len(agents) - 1)


def build_sequential(
    agents: Sequence[str],
    template: ScenarioTemplate,
    target_events: int,
) -> WorkflowBlueprint:
    """
    Linear pipeline: prompt → plan → (retrieve/doc/tool/reason)* → decide.

    Construction: fixed head/tail; pad middle with repeating specialist units
    until target_events is reached.
    """
    bp = WorkflowBlueprint(TopologyId.SEQUENTIAL, notes=["linear chain; each step depends on previous"])
    coord = _pick_agent(agents, ["coordinator", "planner"], 0)
    executor = _pick_agent(agents, ["executor"], len(agents) - 1)
    specialist_idxs = [i for i in range(len(agents)) if i not in (coord, executor)] or [0]

    steps: list[PlannedStep] = [
        PlannedStep("s000", StepKind.PROMPT, coord, produce_artifact=True),
        PlannedStep(
            "s001",
            StepKind.REASONING,
            _pick_agent(agents, ["planner", "coordinator"], coord),
            dep_local_ids=("s000",),
            consume_from=("s000",),
            use_model=True,
        ),
    ]
    prev = "s001"
    unit = 0
    while len(steps) < target_events - 1:
        ag = specialist_idxs[unit % len(specialist_idxs)]
        lid = f"s{len(steps):03d}"
        kinds = [
            (StepKind.RETRIEVAL, False),
            (StepKind.DOCUMENT, False),
            (StepKind.TOOL, True),
            (StepKind.REASONING, False),
            (StepKind.EMBEDDING, False),
        ]
        kind, needs_tool = kinds[unit % len(kinds)]
        tool = template.tools[unit % len(template.tools)] if needs_tool else None
        steps.append(
            PlannedStep(
                lid,
                kind,
                ag,
                dep_local_ids=(prev,),
                consume_from=(prev,),
                tool_name=tool,
                use_model=(kind == StepKind.REASONING),
                memory_tag=(kind == StepKind.RETRIEVAL and unit % 7 == 0),
            )
        )
        prev = lid
        unit += 1

    steps.append(
        PlannedStep(
            f"s{len(steps):03d}",
            StepKind.ACTION,
            executor,
            dep_local_ids=(prev,),
            consume_from=(prev,),
            is_outcome=True,
            produce_artifact=True,
        )
    )
    bp.steps = steps[:target_events]
    # Ensure last is outcome
    if bp.steps:
        bp.steps[-1].is_outcome = True
        bp.steps[-1].kind = StepKind.ACTION
        bp.steps[-1].agent_index = executor
    return bp


def build_hierarchical(
    agents: Sequence[str],
    template: ScenarioTemplate,
    target_events: int,
) -> WorkflowBlueprint:
    """
    Coordinator delegates to specialists; results fan back to coordinator then outcome.

    Construction: root prompt + coordinator plan; wave of specialist tasks each
    depending on the plan; coordinator synthesis depends on all specialists;
    executor depends on synthesis. Pad by adding specialist waves.
    """
    bp = WorkflowBlueprint(
        TopologyId.HIERARCHICAL,
        notes=["coordinator delegates; specialists report; coordinator synthesizes"],
    )
    coord = _pick_agent(agents, ["coordinator"], 0)
    executor = _pick_agent(agents, ["executor"], len(agents) - 1)
    specialists = [i for i in range(len(agents)) if i not in (coord, executor)] or [coord]

    steps: list[PlannedStep] = [
        PlannedStep("s000", StepKind.PROMPT, coord),
        PlannedStep(
            "s001",
            StepKind.REASONING,
            coord,
            dep_local_ids=("s000",),
            consume_from=("s000",),
            use_model=True,
        ),
    ]
    wave = 0
    specialist_leaves: list[str] = []
    while len(steps) < target_events - 2:
        for si, ag in enumerate(specialists):
            if len(steps) >= target_events - 2:
                break
            lid = f"s{len(steps):03d}"
            kind = [StepKind.RETRIEVAL, StepKind.TOOL, StepKind.DOCUMENT, StepKind.REASONING][
                (wave + si) % 4
            ]
            tool = template.tools[(wave + si) % len(template.tools)] if kind == StepKind.TOOL else None
            steps.append(
                PlannedStep(
                    lid,
                    kind,
                    ag,
                    dep_local_ids=("s001",),
                    consume_from=("s001",),
                    tool_name=tool,
                    use_model=(kind == StepKind.REASONING),
                )
            )
            specialist_leaves.append(lid)
        wave += 1
        if wave > 1000:
            break

    if not specialist_leaves:
        specialist_leaves = ["s001"]

    synth_id = f"s{len(steps):03d}"
    steps.append(
        PlannedStep(
            synth_id,
            StepKind.REASONING,
            coord,
            dep_local_ids=tuple(specialist_leaves[-min(len(specialists), len(specialist_leaves)) :]),
            consume_from=tuple(specialist_leaves[-min(len(specialists), len(specialist_leaves)) :]),
            use_model=True,
        )
    )
    steps.append(
        PlannedStep(
            f"s{len(steps):03d}",
            StepKind.ACTION,
            executor,
            dep_local_ids=(synth_id,),
            consume_from=(synth_id,),
            is_outcome=True,
        )
    )
    bp.steps = steps
    return bp


def build_parallel_fan(
    agents: Sequence[str],
    template: ScenarioTemplate,
    target_events: int,
) -> WorkflowBlueprint:
    """
    Fan-out / fan-in: shared prompt, parallel branches, merge, decide.

    Construction: prompt → N parallel branches (retrieve/tool/reason) → merge → action.
    Additional events pad within branches evenly.
    """
    bp = WorkflowBlueprint(
        TopologyId.PARALLEL_FAN,
        notes=["fan-out to parallel branches; fan-in merge before outcome"],
    )
    coord = _pick_agent(agents, ["coordinator", "planner"], 0)
    executor = _pick_agent(agents, ["executor"], len(agents) - 1)
    workers = [i for i in range(len(agents)) if i not in (coord, executor)] or [0]
    n_branches = max(2, min(len(workers), 8))

    steps: list[PlannedStep] = [
        PlannedStep("s000", StepKind.PROMPT, coord),
        PlannedStep(
            "s001",
            StepKind.REASONING,
            coord,
            dep_local_ids=("s000",),
            consume_from=("s000",),
            use_model=True,
        ),
    ]
    budget = max(0, target_events - 4)  # leave room for merge + action
    per_branch = max(1, budget // n_branches)
    branch_leaves: list[str] = []
    for b in range(n_branches):
        prev = "s001"
        ag = workers[b % len(workers)]
        for k in range(per_branch):
            if len(steps) >= target_events - 2:
                break
            lid = f"s{len(steps):03d}"
            kind = [StepKind.RETRIEVAL, StepKind.TOOL, StepKind.DOCUMENT][k % 3]
            tool = template.tools[b % len(template.tools)] if kind == StepKind.TOOL else None
            steps.append(
                PlannedStep(
                    lid,
                    kind,
                    ag,
                    dep_local_ids=(prev,),
                    consume_from=(prev,),
                    tool_name=tool,
                )
            )
            prev = lid
        branch_leaves.append(prev)

    merge_id = f"s{len(steps):03d}"
    steps.append(
        PlannedStep(
            merge_id,
            StepKind.REASONING,
            coord,
            dep_local_ids=tuple(branch_leaves),
            consume_from=tuple(branch_leaves),
            use_model=True,
        )
    )
    steps.append(
        PlannedStep(
            f"s{len(steps):03d}",
            StepKind.ACTION,
            executor,
            dep_local_ids=(merge_id,),
            consume_from=(merge_id,),
            is_outcome=True,
        )
    )
    bp.steps = steps
    return bp


def build_shared_artifact(
    agents: Sequence[str],
    template: ScenarioTemplate,
    target_events: int,
) -> WorkflowBlueprint:
    """
    Shared-artifact: producers write artifacts; multiple consumers reuse them;
    later steps depend on both producers and consumers (via events + artifact links).
    """
    bp = WorkflowBlueprint(
        TopologyId.SHARED_ARTIFACT,
        notes=["explicit shared artifacts consumed by multiple agents"],
    )
    coord = _pick_agent(agents, ["coordinator", "planner"], 0)
    executor = _pick_agent(agents, ["executor"], len(agents) - 1)
    others = [i for i in range(len(agents)) if i not in (coord, executor)] or [0]

    steps: list[PlannedStep] = [
        PlannedStep("s000", StepKind.PROMPT, coord),
        PlannedStep(
            "s001",
            StepKind.DOCUMENT,
            _pick_agent(agents, ["policy", "researcher", "memory"], others[0]),
            dep_local_ids=("s000",),
            consume_from=("s000",),
        ),
    ]
    shared_doc = "s001"
    consumers: list[str] = []
    unit = 0
    while len(steps) < target_events - 1:
        ag = others[unit % len(others)]
        lid = f"s{len(steps):03d}"
        if unit % 3 == 0:
            # New shared producer
            steps.append(
                PlannedStep(
                    lid,
                    StepKind.DOCUMENT if unit % 2 == 0 else StepKind.EMBEDDING,
                    ag,
                    dep_local_ids=(shared_doc,),
                    consume_from=(shared_doc,),
                )
            )
            shared_doc = lid
        else:
            # Consumer of current shared artifact
            steps.append(
                PlannedStep(
                    lid,
                    StepKind.REASONING if unit % 2 else StepKind.TOOL,
                    ag,
                    dep_local_ids=(shared_doc,),
                    consume_from=(shared_doc,),
                    tool_name=template.tools[unit % len(template.tools)] if unit % 2 == 0 else None,
                    use_model=(unit % 2 == 1),
                )
            )
            consumers.append(lid)
        unit += 1

    dep_tail = tuple(consumers[-min(3, len(consumers)) :]) if consumers else (shared_doc,)
    steps.append(
        PlannedStep(
            f"s{len(steps):03d}",
            StepKind.ACTION,
            executor,
            dep_local_ids=dep_tail,
            consume_from=dep_tail,
            is_outcome=True,
        )
    )
    bp.steps = steps
    return bp


def build_delegated(
    agents: Sequence[str],
    template: ScenarioTemplate,
    target_events: int,
) -> WorkflowBlueprint:
    """
    Multi-level delegation: parent invokes child agents via INVOKES relationships.

    Construction: chain of invoke levels; each callee performs work then returns;
    caller depends on callee completion.
    """
    bp = WorkflowBlueprint(
        TopologyId.DELEGATED,
        notes=["multi-level INVOKES delegation; callers depend on callees"],
    )
    coord = _pick_agent(agents, ["coordinator"], 0)
    executor = _pick_agent(agents, ["executor"], len(agents) - 1)
    pool = [i for i in range(len(agents)) if i not in (coord, executor)] or [coord]

    steps: list[PlannedStep] = [
        PlannedStep("s000", StepKind.PROMPT, coord),
        PlannedStep(
            "s001",
            StepKind.REASONING,
            coord,
            dep_local_ids=("s000",),
            consume_from=("s000",),
            use_model=True,
        ),
    ]
    parent = "s001"
    depth = 0
    while len(steps) < target_events - 1:
        callee_ag = pool[depth % len(pool)]
        invoke_step = f"s{len(steps):03d}"
        # Parent records invocation intent
        steps.append(
            PlannedStep(
                invoke_step,
                StepKind.REASONING,
                _agent_of(steps, parent, coord),
                dep_local_ids=(parent,),
                consume_from=(parent,),
                invoke_local_ids=(),  # filled after child id known
                use_model=True,
            )
        )
        child = f"s{len(steps):03d}"
        kind = [StepKind.TOOL, StepKind.RETRIEVAL, StepKind.DOCUMENT, StepKind.REASONING][depth % 4]
        steps.append(
            PlannedStep(
                child,
                kind,
                callee_ag,
                dep_local_ids=(invoke_step,),
                consume_from=(invoke_step,),
                tool_name=template.tools[depth % len(template.tools)] if kind == StepKind.TOOL else None,
            )
        )
        # Patch invoke targets on the invoke step
        steps[-2].invoke_local_ids = (child,)
        parent = child
        depth += 1

    steps.append(
        PlannedStep(
            f"s{len(steps):03d}",
            StepKind.ACTION,
            executor,
            dep_local_ids=(parent,),
            consume_from=(parent,),
            is_outcome=True,
        )
    )
    bp.steps = steps
    return bp


def _agent_of(steps: list[PlannedStep], local_id: str, default: int) -> int:
    for s in steps:
        if s.local_id == local_id:
            return s.agent_index
    return default


def build_mixed(
    agents: Sequence[str],
    template: ScenarioTemplate,
    target_events: int,
) -> WorkflowBlueprint:
    """
    Mixed realistic: prompt, hierarchical delegation, parallel evidence, shared
    artifact reuse, optional retry, then decision.
    """
    bp = WorkflowBlueprint(
        TopologyId.MIXED,
        notes=["combines parallel evidence, shared artifacts, delegation, and retry"],
    )
    # Start from parallel skeleton then splice retries / shared docs
    base = build_parallel_fan(agents, template, max(12, target_events - 8))
    steps = list(base.steps)
    # Drop trailing action temporarily
    outcome = steps.pop() if steps and steps[-1].is_outcome else None
    merge = steps[-1] if steps else None

    # Insert shared document + consumers
    shared = PlannedStep(
        f"s{len(steps):03d}",
        StepKind.DOCUMENT,
        _pick_agent(agents, ["policy", "memory", "researcher"], 0),
        dep_local_ids=("s000",),
        consume_from=("s000",),
    )
    steps.append(shared)
    tool_retry_parent = PlannedStep(
        f"s{len(steps):03d}",
        StepKind.TOOL,
        _pick_agent(agents, ["tool_runner", "researcher"], 1 % len(agents)),
        dep_local_ids=(shared.local_id,),
        consume_from=(shared.local_id,),
        tool_name=template.tools[0],
    )
    steps.append(tool_retry_parent)
    retry = PlannedStep(
        f"s{len(steps):03d}",
        StepKind.TOOL,
        tool_retry_parent.agent_index,
        dep_local_ids=(tool_retry_parent.local_id,),
        consume_from=(tool_retry_parent.local_id,),
        tool_name=template.tools[0],
        retry_of=tool_retry_parent.local_id,
    )
    steps.append(retry)

    # Delegation snippet
    invoke = PlannedStep(
        f"s{len(steps):03d}",
        StepKind.REASONING,
        _pick_agent(agents, ["coordinator"], 0),
        dep_local_ids=(retry.local_id,),
        consume_from=(retry.local_id,),
        use_model=True,
    )
    steps.append(invoke)
    callee = PlannedStep(
        f"s{len(steps):03d}",
        StepKind.RETRIEVAL,
        _pick_agent(agents, ["researcher", "analyst"], 1 % len(agents)),
        dep_local_ids=(invoke.local_id,),
        consume_from=(invoke.local_id,),
        memory_tag=True,
    )
    steps.append(callee)
    invoke.invoke_local_ids = (callee.local_id,)

    # Pad if needed
    pad_prev = callee.local_id
    workers = list(range(len(agents)))
    u = 0
    while len(steps) < target_events - 1:
        lid = f"s{len(steps):03d}"
        steps.append(
            PlannedStep(
                lid,
                [StepKind.REASONING, StepKind.TOOL, StepKind.DOCUMENT][u % 3],
                workers[u % len(workers)],
                dep_local_ids=(pad_prev,),
                consume_from=(pad_prev,),
                tool_name=template.tools[u % len(template.tools)] if u % 3 == 1 else None,
                use_model=(u % 3 == 0),
            )
        )
        pad_prev = lid
        u += 1

    merge_deps = [pad_prev]
    if merge is not None:
        merge_deps.append(merge.local_id)
    final = PlannedStep(
        f"s{len(steps):03d}",
        StepKind.ACTION,
        _pick_agent(agents, ["executor"], len(agents) - 1),
        dep_local_ids=tuple(merge_deps),
        consume_from=tuple(merge_deps),
        is_outcome=True,
    )
    steps.append(final)
    if outcome is not None:
        # already replaced
        pass
    bp.steps = steps
    return bp


_BUILDERS: dict[TopologyId, Callable[..., WorkflowBlueprint]] = {
    TopologyId.SEQUENTIAL: build_sequential,
    TopologyId.HIERARCHICAL: build_hierarchical,
    TopologyId.PARALLEL_FAN: build_parallel_fan,
    TopologyId.SHARED_ARTIFACT: build_shared_artifact,
    TopologyId.DELEGATED: build_delegated,
    TopologyId.MIXED: build_mixed,
}


def build_topology(
    topology_id: TopologyId | str,
    agents: Sequence[str],
    template: ScenarioTemplate,
    target_events: int,
) -> WorkflowBlueprint:
    if isinstance(topology_id, str):
        topology_id = TopologyId(topology_id)
    if target_events < 4:
        raise ValueError("target_events must be >= 4")
    builder = _BUILDERS[topology_id]
    return builder(agents, template, target_events)


def list_topologies() -> tuple[TopologyId, ...]:
    return tuple(TopologyId)
