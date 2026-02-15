import networkx as nx


def run_responsibility_propagation(graph, outcome_node):

    # Initialize responsibility scores
    responsibility = {node: 0.0 for node in graph.nodes()}
    responsibility[outcome_node] = 1.0

    # Reverse topological order (backward traversal)
    topo_order = list(nx.topological_sort(graph))
    topo_order.reverse()

    for node in topo_order:

        incoming_edges = list(graph.in_edges(node, data=True))

        if not incoming_edges:
            continue

        total_weight = sum(edge[2]["weight"] for edge in incoming_edges) + 1e-6

        for parent, _, data in incoming_edges:

            weight = data["weight"]

            propagated_score = responsibility[node] * (weight / total_weight)

            responsibility[parent] += propagated_score

    return responsibility
