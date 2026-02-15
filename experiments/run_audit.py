from provenance_graph.graph_builder import MLPGBuilder
from audit_integrity.chain_builder import build_hash_chain
from audit_integrity.tamper_simulator import tamper_with_event
from audit_integrity.integrity_verifier import verify_integrity
from audit_integrity.audit_report import print_audit_report

EVENT_PATH = "data/raw_events/events.json"


def main():

    builder = MLPGBuilder()
    builder.load_events(EVENT_PATH)
    graph = builder.build_graph()

    print("\nBuilding provenance hash chain...")
    stored_hashes = build_hash_chain(graph)

    # Verify original chain
    valid, node = verify_integrity(graph, stored_hashes)
    print_audit_report(valid, node)

    # Tamper simulation
    tampered_node = list(graph.nodes())[3]

    graph = tamper_with_event(graph, tampered_node)

    # Re-verify
    valid, node = verify_integrity(graph, stored_hashes)
    print_audit_report(valid, node)


if __name__ == "__main__":
    main()
