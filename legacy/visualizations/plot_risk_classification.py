import matplotlib.pyplot as plt

trust_score = 0.467

labels = ["Risk", "Trust"]
values = [1-trust_score, trust_score]

plt.figure(figsize=(6,6))
plt.pie(
    values,
    labels=labels,
    autopct="%1.1f%%",
    startangle=90
)

plt.title("Decision Trust vs Risk Composition")
plt.savefig("trust_risk_pie.pdf", dpi=300)
plt.show()
