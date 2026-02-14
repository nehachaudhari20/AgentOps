# simulation/fault_injector.py

def inject_fault(events, fault_agent="Researcher"):

    for event in events:
        if event.agent_id == fault_agent:
            event.output_data = "Credit score: 450 (Incorrect data)"
            event.metadata["fault_injected"] = True

    return events
