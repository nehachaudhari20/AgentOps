from provenance_graph.graph_builder import MLPGBuilder
from attribution.rpa_algorithm import compute_rpa
from attribution.attribution_aggregator import aggregate_by_agent
from accountability.mfav_calculator import compute_mfav
from accountability.accountability_report import print_mfav_report

EVENT_PATH = "data/raw_events/events.json"


def main():

    builder = MLPGBuilder()
    builder.load_events(EVENT_PATH)
    graph = builder.build_graph()

    outcome_node, node_scores = compute_rpa(graph)

    print("\nNode Responsibility Scores:")
    for node, score in sorted(
        node_scores.items(),
        key=lambda x: x[1],
        reverse=True
    ):
        agent = graph.nodes[node]["agent"]
        ntype = graph.nodes[node]["type"]
        print(f"{agent} ({ntype}): {score:.3f}")

    # Agent aggregation
    agent_scores = aggregate_by_agent(graph, node_scores)

    print("\nAgent Attribution:")
    for agent, score in sorted(
        agent_scores.items(),
        key=lambda x: x[1],
        reverse=True
    ):
        print(f"{agent}: {score:.3f}")

    # MFAV computation
    mfav_scores = compute_mfav(graph, node_scores)

    print_mfav_report(mfav_scores)


if __name__ == "__main__":
    main()
