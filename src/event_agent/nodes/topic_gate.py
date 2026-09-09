"""Два терминальных узла после classify_topic: keep_record / discard_record."""
import logging
from event_agent.graph.state import CrawlState

log = logging.getLogger(__name__)


def keep_record_node(state: CrawlState) -> dict:
    record = state["current_record"]
    log.info("KEEP (about ПЦ): %s", record.url)
    return {"all_records": [record]}


def discard_record_node(state: CrawlState) -> dict:
    record = state.get("current_record")
    url = record.url if record else "unknown"
    log.info("DISCARD (not about ПЦ - %s): %s", state.get("topic_reason"), url)
    return {}
