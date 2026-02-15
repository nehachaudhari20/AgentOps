from provenance_graph.graph_builder import MLPGBuilder
from attribution.rpa_algorithm import compute_rpa
from attribution.attribution_aggregator import aggregate_by_agent

EVENT_PATH = "data/raw_events/events.json"


def main():

    # Build MLPG
    builder = MLPGBuilder()
    builder.load_events(EVENT_PATH)
    graph = builder.build_graph()

    # Run RPA
    outcome_node, node_scores = compute_rpa(graph)

    print("\nOutcome Node:", outcome_node)

    print("\nNode Responsibility Scores:")
    for node, score in sorted(node_scores.items(), key=lambda x: x[1], reverse=True):
        print(f"{graph.nodes[node]['agent']} ({graph.nodes[node]['type']}): {score:.3f}")

    # Aggregate by agent
    agent_scores = aggregate_by_agent(graph, node_scores)

    print("\nAgent Responsibility Attribution:")
    for agent, score in sorted(agent_scores.items(), key=lambda x: x[1], reverse=True):
        print(f"{agent}: {score:.3f}")


if __name__ == "__main__":
    main()
