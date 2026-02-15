import matplotlib.pyplot as plt


def plot_mfav_pie(mfav_scores,
                  save_path="outputs/fig_mfav_pie.pdf"):

    labels = list(mfav_scores.keys())
    values = list(mfav_scores.values())

    plt.figure(figsize=(7, 7))
    plt.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=120
    )

    plt.title("MFAV Accountability Distribution")
    plt.savefig(save_path, dpi=300)
    plt.show()
