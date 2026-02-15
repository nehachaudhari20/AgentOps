from audit_integrity.hash_engine import compute_event_hash


def build_hash_chain(graph):

    hash_store = {}

    topo_order = list(graph.nodes())

    for node in topo_order:

        event_data = graph.nodes[node]

        parents = list(graph.predecessors(node))

        parent_hashes = [
            hash_store[p] for p in parents
            if p in hash_store
        ]

        h = compute_event_hash(event_data, parent_hashes)

        hash_store[node] = h

    return hash_store
