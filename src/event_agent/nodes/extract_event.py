import logging
from event_agent.graph.state import EventTask
from event_agent.tools.parser import extract_event

log = logging.getLogger(__name__)


def extract_event_node(payload: EventTask) -> dict:
    log.info("Extracting event: %s", payload["url"])
    record = extract_event(payload["url"])
    return {"all_records": [record]}
