from attribution.propagation_engine import run_responsibility_propagation


def compute_rpa(graph):

    # Identify outcome node (Executor action)
    outcome_nodes = [
        n for n in graph.nodes()
        if graph.nodes[n]["type"] == "action"
    ]

    if not outcome_nodes:
        raise ValueError("No outcome node found.")

    outcome_node = outcome_nodes[0]

    node_responsibility = run_responsibility_propagation(
        graph,
        outcome_node
    )

    return outcome_node, node_responsibility
