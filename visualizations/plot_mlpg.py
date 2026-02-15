import matplotlib.pyplot as plt
import networkx as nx


def build_node_labels(graph):

    labels = {}

    for node, data in graph.nodes(data=True):

        agent = data.get("agent", "Unknown")
        ntype = data.get("type", "")

        # Clean label format
        label = f"{agent}\n({ntype})"

        labels[node] = label

    return labels


def plot_mlpg(graph, save_path="outputs/fig_mlpg.pdf"):

    plt.figure(figsize=(14, 8))

    pos = nx.spring_layout(graph, seed=42, k=0.8)

    # Node colors by type
    node_colors = []

    for _, data in graph.nodes(data=True):

        ntype = data.get("type", "")

        if ntype == "prompt":
            node_colors.append("lightgreen")
        elif ntype == "reasoning":
            node_colors.append("skyblue")
        elif ntype in ["retrieval", "document"]:
            node_colors.append("orange")
        elif ntype == "embedding":
            node_colors.append("purple")
        elif ntype == "tool_call":
            node_colors.append("pink")
        elif ntype == "action":
            node_colors.append("red")
        else:
            node_colors.append("gray")

    # Build readable labels
    labels = build_node_labels(graph)

    nx.draw(
        graph,
        pos,
        labels=labels,
        node_size=2200,
        node_color=node_colors,
        font_size=8,
        arrows=True
    )

    plt.title("Multi-Layer Provenance Graph (MLPG)")
    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
