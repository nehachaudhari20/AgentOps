import hashlib
import json


def compute_event_hash(event_data, parent_hashes):

    payload = json.dumps(
        event_data,
        sort_keys=True
    )

    parent_concat = "".join(sorted(parent_hashes))

    full_string = payload + parent_concat

    return hashlib.sha256(
        full_string.encode()
    ).hexdigest()
