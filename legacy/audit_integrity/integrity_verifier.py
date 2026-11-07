from audit_integrity.hash_engine import compute_event_hash


def verify_integrity(graph, stored_hashes):

    recomputed = {}

    for node in graph.nodes():

        event_data = graph.nodes[node]

        parents = list(graph.predecessors(node))

        parent_hashes = [
            recomputed[p]
            for p in parents
            if p in recomputed
        ]

        h = compute_event_hash(event_data, parent_hashes)

        recomputed[node] = h

        if stored_hashes[node] != h:
            return False, node

    return True, None
