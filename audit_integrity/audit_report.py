def print_audit_report(is_valid, node):

    print("\nAudit Integrity Report:")

    if is_valid:
        print("✔ Provenance chain intact.")
    else:
        print(f"✖ Tampering detected at node: {node}")
