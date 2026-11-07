import matplotlib.pyplot as plt


def plot_mfav(mfav_scores,
              save_path="outputs/fig_mfav_bar.pdf"):

    labels = list(mfav_scores.keys())
    values = list(mfav_scores.values())

    plt.figure(figsize=(8, 5))
    plt.bar(labels, values)

    plt.ylabel("Accountability Share")
    plt.title("Multi-Factor Accountability Vector (MFAV)")

    plt.savefig(save_path, dpi=300, bbox_inches="tight")
    plt.show()
