import json
import networkx as nx

from provenance_graph.node_factory import ProvenanceNode
from provenance_graph.edge_constructor import construct_edges
from provenance_graph.weight_calculator import compute_edge_weights


class MLPGBuilder:

    def __init__(self):
        self.graph = nx.DiGraph()
        self.nodes = []

    def load_events(self, path):

        with open(path, "r") as f:
            events = json.load(f)

        for e in events:
            node = ProvenanceNode(e)
            self.nodes.append(node)

    def build_graph(self):

        for node in self.nodes:

            self.graph.add_node(
                node.id,
                agent=node.agent,
                type=node.type,
                layer=node.layer
            )

        self.graph = construct_edges(self.graph, self.nodes)
        self.graph = compute_edge_weights(self.graph)

        return self.graph
