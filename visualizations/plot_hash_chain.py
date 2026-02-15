import matplotlib.pyplot as plt


def plot_hash_chain(hash_store):

    nodes = list(hash_store.keys())
    hashes = list(hash_store.values())

    plt.figure(figsize=(12, 5))

    plt.plot(range(len(nodes)), range(len(nodes)))

    plt.title("Provenance-Linked Hash Chain")
    plt.xlabel("Event Index")
    plt.ylabel("Hash Linkage")

    plt.show()
