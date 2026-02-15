from collections import defaultdict
from accountability.entity_mapper import map_node_to_factor


def compute_mfav(graph, node_scores):

    factor_scores = defaultdict(float)

    for node, score in node_scores.items():

        node_type = graph.nodes[node]["type"]
        agent = graph.nodes[node]["agent"]

        factor = map_node_to_factor(node_type, agent)

        factor_scores[factor] += score

    # Normalize
    total = sum(factor_scores.values()) + 1e-6

    for factor in factor_scores:
        factor_scores[factor] /= total

    return dict(factor_scores)
