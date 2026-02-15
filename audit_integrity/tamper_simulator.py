def tamper_with_event(graph, node_id):

    print(f"\nTampering with node: {node_id}")

    # Modify output field
    graph.nodes[node_id]["output"] = "TAMPERED_DATA"

    return graph
