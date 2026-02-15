import random


def compute_edge_weights(graph):

    for u, v in graph.edges():

        source_type = graph.nodes[u]["type"]

        if source_type == "document":
            w = random.uniform(0.7, 1.0)

        elif source_type == "prompt":
            w = random.uniform(0.4, 0.6)

        elif source_type == "tool_call":
            w = random.uniform(0.8, 1.0)

        else:
            w = random.uniform(0.3, 0.5)

        graph[u][v]["weight"] = w

    return graph
