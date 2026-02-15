from collections import defaultdict


def aggregate_by_agent(graph, node_scores):

    agent_scores = defaultdict(float)

    for node, score in node_scores.items():

        agent = graph.nodes[node]["agent"]

        agent_scores[agent] += score

    # Normalize
    total = sum(agent_scores.values()) + 1e-6

    for agent in agent_scores:
        agent_scores[agent] /= total

    return dict(agent_scores)
