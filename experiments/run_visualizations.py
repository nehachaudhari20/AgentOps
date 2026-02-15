# -------------------------------
# Governance Visualization Runner
# -------------------------------

from provenance_graph.graph_builder import MLPGBuilder
from attribution.rpa_algorithm import compute_rpa
from attribution.attribution_aggregator import aggregate_by_agent
from accountability.mfav_calculator import compute_mfav
from trust_scoring.trust_model import compute_trust_score

# Bar / graph plots
from visualizations.plot_mlpg import plot_mlpg
from visualizations.plot_responsibility_heatmap import plot_responsibility
from visualizations.plot_agent_attribution import plot_agent_attribution
from visualizations.plot_mfav import plot_mfav
from visualizations.plot_trust_components import plot_trust_components

# Pie charts
from visualizations.plot_agent_pie import plot_agent_pie
from visualizations.plot_mfav_pie import plot_mfav_pie
from visualizations.plot_trust_pie import plot_trust_pie


EVENT_PATH = "data/raw_events/events.json"


def main():

    print("\n🔹 Building MLPG...")

    builder = MLPGBuilder()
    builder.load_events(EVENT_PATH)
    graph = builder.build_graph()

    # -------------------------------
    # MLPG Visualization
    # -------------------------------
    plot_mlpg(graph)

    print("\n🔹 Running Responsibility Propagation...")

    outcome_node, node_scores = compute_rpa(graph)

    # -------------------------------
    # Responsibility Heatmap
    # -------------------------------
    plot_responsibility(node_scores)

    print("\n🔹 Computing Agent Attribution...")

    agent_scores = aggregate_by_agent(graph, node_scores)

    # Bar + Pie
    plot_agent_attribution(agent_scores)
    plot_agent_pie(agent_scores)

    print("\n🔹 Computing MFAV...")

    mfav_scores = compute_mfav(graph, node_scores)

    # Bar + Pie
    plot_mfav(mfav_scores)
    plot_mfav_pie(mfav_scores)

    print("\n🔹 Computing Trust Score...")

    trust_result = compute_trust_score(graph, node_scores)

    components = trust_result["components"]

    # Bar + Pie
    plot_trust_components(components)
    plot_trust_pie(components)

    print("\n✅ All visualizations generated successfully.")


if __name__ == "__main__":
    main()
