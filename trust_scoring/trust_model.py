import numpy as np

from trust_scoring.feature_extractor import (
    compute_evidence_strength,
    compute_causality_confidence,
    compute_tool_reliability,
    compute_policy_compliance,
    compute_model_confidence
)


def compute_trust_score(graph, node_scores):

    E = compute_evidence_strength(graph, node_scores)
    C = compute_causality_confidence(node_scores)
    T_r = compute_tool_reliability(graph, node_scores)
    P = compute_policy_compliance()
    M_c = compute_model_confidence()

    # Weights (can be learned later)
    weights = {
        "E": 0.25,
        "C": 0.25,
        "T_r": 0.20,
        "P": 0.15,
        "M_c": 0.15
    }

    score = (
        weights["E"] * E +
        weights["C"] * C +
        weights["T_r"] * T_r +
        weights["P"] * P +
        weights["M_c"] * M_c
    )

    return {
        "trust_score": score,
        "components": {
            "Evidence": E,
            "Causality": C,
            "ToolReliability": T_r,
            "PolicyCompliance": P,
            "ModelConfidence": M_c
        }
    }
