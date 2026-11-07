import matplotlib.pyplot as plt
import networkx as nx


def visualize_graph(graph):

    pos = nx.spring_layout(graph, seed=42)

    color_map = {
        1: "lightblue",
        2: "lightgreen",
        3: "orange",
        4: "pink",
        5: "red"
    }

    node_colors = [
        color_map[graph.nodes[n]["layer"]]
        for n in graph.nodes()
    ]

    labels = {
        n: f"{graph.nodes[n]['agent']}\n{graph.nodes[n]['type']}"
        for n in graph.nodes()
    }

    nx.draw(
        graph,
        pos,
        labels=labels,
        node_color=node_colors,
        node_size=2500,
        font_size=8,
        arrows=True
    )

    plt.title("Full Multi-Layer Provenance Graph (MLPG)")
    plt.show()
