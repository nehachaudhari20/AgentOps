from provenance_graph.graph_builder import MLPGBuilder
from provenance_graph.graph_visualizer import visualize_graph

EVENT_PATH = "data/raw_events/events.json"


def main():

    builder = MLPGBuilder()

    builder.load_events(EVENT_PATH)

    graph = builder.build_graph()

    print("Nodes:", graph.number_of_nodes())
    print("Edges:", graph.number_of_edges())

    visualize_graph(graph)


if __name__ == "__main__":
    main()
