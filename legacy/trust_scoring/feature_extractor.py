import numpy as np


def compute_evidence_strength(graph, node_scores):

    evidence_nodes = [
        n for n in graph.nodes()
        if graph.nodes[n]["type"] in ["document", "embedding"]
    ]

    if not evidence_nodes:
        return 0.0

    scores = [node_scores[n] for n in evidence_nodes]

    return np.mean(scores)


def compute_causality_confidence(node_scores):

    values = np.array(list(node_scores.values()))

    # Normalize
    values = values / (values.sum() + 1e-6)

    entropy = -np.sum(values * np.log(values + 1e-9))

    max_entropy = np.log(len(values))

    confidence = 1 - (entropy / max_entropy)

    return confidence


def compute_tool_reliability(graph, node_scores):

    tool_nodes = [
        n for n in graph.nodes()
        if graph.nodes[n]["type"] == "tool_call"
    ]

    if not tool_nodes:
        return 0.0

    scores = [node_scores[n] for n in tool_nodes]

    return np.mean(scores)


def compute_policy_compliance():

    # Prototype: assume compliant
    return 0.9


def compute_model_confidence():

    # Prototype placeholder
    return 0.8
