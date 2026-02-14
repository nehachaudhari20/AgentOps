# simulation/workflow_generator.py

from simulation.event_schema import Event

def generate_workflow():

    events = []

    # Planner agent
    e1 = Event.create(
        agent_id="Planner",
        event_type="reasoning",
        input_data="User asks for loan approval decision",
        output_data="Plan: retrieve credit data → risk assess → approve/reject"
    )
    events.append(e1)

    # Research agent retrieval
    e2 = Event.create(
        agent_id="Researcher",
        event_type="retrieval",
        input_data="Fetch credit score and financial history",
        output_data="Credit score: 720, Income stable",
        dependencies=[e1.event_id]
    )
    events.append(e2)

    # Tool agent
    e3 = Event.create(
        agent_id="ToolAgent",
        event_type="tool_call",
        input_data="Run risk calculation API",
        output_data="Risk score: LOW",
        dependencies=[e2.event_id]
    )
    events.append(e3)

    # Executor agent
    e4 = Event.create(
        agent_id="Executor",
        event_type="action",
        input_data="Loan decision",
        output_data="Loan Approved",
        dependencies=[e3.event_id]
    )
    events.append(e4)

    return events
