import matplotlib.pyplot as plt
import numpy as np


def plot_responsibility(node_scores,
                        save_path="outputs/fig_responsibility_heatmap.pdf"):

    nodes = list(node_scores.keys())
    scores = list(node_scores.values())

    colors = plt.cm.Reds(np.array(scores))

    plt.figure(figsize=(12, 5))
    plt.bar(nodes, scores, color=colors)

    plt.xticks(rotation=75)
    plt.ylabel("Responsibility Score")
    plt.title("Responsibility Propagation Heatmap")

    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
