class ProvenanceNode:

    def __init__(self, event):

        self.id = event["event_id"]
        self.agent = event["agent_id"]
        self.type = event["event_type"]
        self.dependencies = event["dependencies"]

        self.layer = self.assign_layer()

    def assign_layer(self):

        mapping = {
            "reasoning": 1,
            "prompt": 2,
            "retrieval": 3,
            "document": 3,
            "embedding": 3,
            "tool_call": 4,
            "action": 5
        }

        return mapping.get(self.type, 1)
