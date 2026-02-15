import matplotlib.pyplot as plt


def plot_trust_pie(components,
                   save_path="outputs/fig_trust_components_pie.pdf"):

    labels = list(components.keys())
    values = list(components.values())

    plt.figure(figsize=(7, 7))
    plt.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90
    )

    plt.title("Trust Score Composition")
    plt.savefig(save_path, dpi=300)
    plt.show()
