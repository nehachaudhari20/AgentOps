import matplotlib.pyplot as plt


def plot_agent_attribution(agent_scores,
                           save_path="outputs/fig_agent_attribution_bar.pdf"):

    agents = list(agent_scores.keys())
    scores = list(agent_scores.values())

    plt.figure(figsize=(10, 5))
    plt.bar(agents, scores)

    plt.xticks(rotation=45)
    plt.ylabel("Responsibility")
    plt.title("Agent Responsibility Attribution")

    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
