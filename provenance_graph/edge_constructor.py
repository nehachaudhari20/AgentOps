def construct_edges(graph, nodes):

    node_map = {node.id: node for node in nodes}

    for node in nodes:
        for dep in node.dependencies:
            if dep in node_map:
                graph.add_edge(dep, node.id, weight=1.0)

    return graph
