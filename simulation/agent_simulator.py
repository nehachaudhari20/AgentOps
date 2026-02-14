# simulation/agent_simulator.py

import json
from simulation.workflow_generator import generate_workflow
from simulation.fault_injector import inject_fault

OUTPUT_PATH = "data/raw_events/events.json"

def run_simulation(inject_error=False):

    events = generate_workflow()

    if inject_error:
        events = inject_fault(events)

    # Convert to dict for JSON storage
    event_dicts = [event.__dict__ for event in events]

    with open(OUTPUT_PATH, "w") as f:
        json.dump(event_dicts, f, indent=4)

    print(f"Simulation complete. {len(events)} events saved.")


if __name__ == "__main__":
    run_simulation(inject_error=True)
