from simulation.event_schema import Event


def generate_full_workflow():

    events = []

    # 1️⃣ User Prompt
    user_prompt = Event.create(
        "User",
        "prompt",
        "Loan request",
        "Approve my loan application"
    )
    events.append(user_prompt)

    # 2️⃣ System Prompt
    system_prompt = Event.create(
        "System",
        "prompt",
        "Policy template",
        "Follow risk evaluation policy",
        dependencies=[user_prompt.event_id]
    )
    events.append(system_prompt)

    # 3️⃣ Planner Reasoning
    planner = Event.create(
        "Planner",
        "reasoning",
        "Analyze loan",
        "Retrieve credit data",
        dependencies=[system_prompt.event_id]
    )
    events.append(planner)

    # 4️⃣ Retrieval Query
    retrieval = Event.create(
        "Researcher",
        "retrieval",
        "Fetch credit score",
        "Query KB",
        dependencies=[planner.event_id]
    )
    events.append(retrieval)

    # 5️⃣ Documents
    doc1 = Event.create(
        "KB",
        "document",
        "Credit history",
        "Score 720",
        dependencies=[retrieval.event_id]
    )

    doc2 = Event.create(
        "KB",
        "document",
        "Income history",
        "Stable income",
        dependencies=[retrieval.event_id]
    )

    events.extend([doc1, doc2])

    # 6️⃣ Embeddings
    emb1 = Event.create(
        "Embedder",
        "embedding",
        "Vectorize doc1",
        "Vector D1",
        dependencies=[doc1.event_id]
    )

    emb2 = Event.create(
        "Embedder",
        "embedding",
        "Vectorize doc2",
        "Vector D2",
        dependencies=[doc2.event_id]
    )

    events.extend([emb1, emb2])

    # 7️⃣ Research synthesis
    research = Event.create(
        "Researcher",
        "reasoning",
        "Analyze docs",
        "Low risk",
        dependencies=[emb1.event_id, emb2.event_id]
    )
    events.append(research)

    # 8️⃣ Tool output
    tool = Event.create(
        "ToolAgent",
        "tool_call",
        "Risk API",
        "Risk LOW",
        dependencies=[research.event_id]
    )
    events.append(tool)

    # 9️⃣ Final action
    executor = Event.create(
        "Executor",
        "action",
        "Loan decision",
        "Loan Approved",
        dependencies=[tool.event_id]
    )
    events.append(executor)

    return events
