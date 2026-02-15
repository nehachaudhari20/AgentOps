def classify_risk(trust_score):

    if trust_score > 0.8:
        return "LOW RISK"

    elif trust_score > 0.5:
        return "MEDIUM RISK"

    else:
        return "HIGH RISK"
