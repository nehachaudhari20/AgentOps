from simulation.event_schema import Event


def generate_branched_workflow():

    events = []

    # -------------------------
    # PROMPT LAYER
    # -------------------------

    user_prompt = Event.create(
        "User",
        "prompt",
        "Loan request",
        "Approve my loan"
    )
    events.append(user_prompt)

    system_prompt = Event.create(
        "System",
        "prompt",
        "Loan policy template",
        "Follow risk protocol",
        dependencies=[user_prompt.event_id]
    )
    events.append(system_prompt)

    policy_doc = Event.create(
        "PolicyEngine",
        "document",
        "Bank policy",
        "Debt-income ratio rules",
        dependencies=[system_prompt.event_id]
    )
    events.append(policy_doc)

    # -------------------------
    # REASONING LAYER
    # -------------------------

    planner = Event.create(
        "Planner",
        "reasoning",
        "Analyze loan",
        "Retrieve financial + legal data",
        dependencies=[system_prompt.event_id, policy_doc.event_id]
    )
    events.append(planner)

    # -------------------------
    # MEMORY INFLUENCE
    # -------------------------

    memory = Event.create(
        "Memory",
        "retrieval",
        "Past loan cases",
        "Historical approvals",
        dependencies=[planner.event_id]
    )
    events.append(memory)

    # -------------------------
    # RETRIEVAL BRANCH
    # -------------------------

    retrieval = Event.create(
        "Researcher",
        "retrieval",
        "Fetch KB data",
        "Financial + legal docs",
        dependencies=[planner.event_id]
    )
    events.append(retrieval)

    financial_doc = Event.create(
        "KB",
        "document",
        "Financial history",
        "Credit score 720",
        dependencies=[retrieval.event_id]
    )

    legal_doc = Event.create(
        "KB",
        "document",
        "Legal compliance",
        "No legal risk",
        dependencies=[retrieval.event_id]
    )

    events.extend([financial_doc, legal_doc])

    # -------------------------
    # EMBEDDINGS
    # -------------------------

    emb1 = Event.create(
        "Embedder",
        "embedding",
        "Vectorize financial doc",
        "Vector F",
        dependencies=[financial_doc.event_id]
    )

    emb2 = Event.create(
        "Embedder",
        "embedding",
        "Vectorize legal doc",
        "Vector L",
        dependencies=[legal_doc.event_id]
    )

    events.extend([emb1, emb2])

    # -------------------------
    # RESEARCH SYNTHESIS
    # -------------------------

    research = Event.create(
        "Researcher",
        "reasoning",
        "Synthesize evidence",
        "Low risk",
        dependencies=[emb1.event_id, emb2.event_id, memory.event_id]
    )
    events.append(research)

    # -------------------------
    # TOOL BRANCH
    # -------------------------

    risk_tool = Event.create(
        "RiskTool",
        "tool_call",
        "Risk API",
        "Risk LOW",
        dependencies=[research.event_id]
    )

    compliance_tool = Event.create(
        "ComplianceTool",
        "tool_call",
        "Compliance API",
        "Compliant",
        dependencies=[research.event_id]
    )

    events.extend([risk_tool, compliance_tool])

    # -------------------------
    # FINAL ACTION
    # -------------------------

    executor = Event.create(
        "Executor",
        "action",
        "Loan decision",
        "Loan Approved",
        dependencies=[risk_tool.event_id, compliance_tool.event_id]
    )

    events.append(executor)

    return events
