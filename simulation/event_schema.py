# simulation/event_schema.py

from dataclasses import dataclass
from typing import List, Optional
import uuid
import time

@dataclass
class Event:
    event_id: str
    agent_id: str
    event_type: str
    input_data: str
    output_data: str
    dependencies: List[str]
    timestamp: float
    metadata: Optional[dict] = None

    @staticmethod
    def create(agent_id, event_type, input_data, output_data, dependencies=None, metadata=None):
        return Event(
            event_id=str(uuid.uuid4()),
            agent_id=agent_id,
            event_type=event_type,
            input_data=input_data,
            output_data=output_data,
            dependencies=dependencies or [],
            timestamp=time.time(),
            metadata=metadata or {}
        )
