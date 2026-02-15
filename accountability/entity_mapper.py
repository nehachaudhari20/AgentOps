def map_node_to_factor(node_type, agent_name):

    # Factor categories

    if node_type in ["reasoning"]:
        return "agent"

    if node_type in ["prompt"]:
        return "prompt"

    if node_type in ["document", "embedding"]:
        return "data"

    if node_type in ["tool_call"]:
        return "tool"

    if agent_name == "Memory":
        return "memory"

    if node_type in ["retrieval"]:
        return "data"

    if node_type in ["action"]:
        return "execution"

    return "other"
