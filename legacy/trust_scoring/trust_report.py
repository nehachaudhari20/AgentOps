def print_trust_report(trust_result):

    score = trust_result["trust_score"]
    components = trust_result["components"]

    print("\nTrust Score:", round(score, 3))
    print("\nComponent Breakdown:")

    for k, v in components.items():
        print(f"{k:<18} → {v:.3f}")
