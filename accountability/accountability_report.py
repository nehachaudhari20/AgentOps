def print_mfav_report(mfav_scores):

    print("\nMulti-Factor Accountability Vector (MFAV):\n")

    for factor, score in sorted(
        mfav_scores.items(),
        key=lambda x: x[1],
        reverse=True
    ):
        print(f"{factor.upper():<12} → {score:.3f}")
