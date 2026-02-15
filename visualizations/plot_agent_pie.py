import matplotlib.pyplot as plt


def plot_agent_pie(agent_scores,
                   save_path="outputs/fig_agent_attribution_pie.pdf"):

    labels = list(agent_scores.keys())
    values = list(agent_scores.values())

    plt.figure(figsize=(8, 8))
    plt.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=140
    )

    plt.title("Agent Responsibility Distribution")
    plt.savefig(save_path, dpi=300)
    plt.show()
