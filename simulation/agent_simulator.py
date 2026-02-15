import json
import os

from simulation.workflow_generator import generate_full_workflow
from simulation.branched_workflow_generator import generate_branched_workflow


OUTPUT_PATH = "data/raw_events/events.json"


def run_simulation():

    events = generate_branched_workflow()

    os.makedirs("data/raw_events", exist_ok=True)

    with open(OUTPUT_PATH, "w") as f:
        json.dump([e.__dict__ for e in events], f, indent=4)

    print(f"Generated {len(events)} events.")


if __name__ == "__main__":
    run_simulation()
