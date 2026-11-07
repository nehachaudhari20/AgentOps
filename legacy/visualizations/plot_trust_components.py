import matplotlib.pyplot as plt


def plot_trust_components(components,
                          save_path="outputs/fig_trust_components_bar.pdf"):

    labels = list(components.keys())
    values = list(components.values())

    plt.figure(figsize=(8, 5))
    plt.bar(labels, values)

    plt.ylabel("Signal Strength")
    plt.title("Trust Score Component Contributions")

    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
