"""Узел графа: определяет, действительно ли извлечённая статья про Президентский
центр (ПЦ). Результат используется условным edge для выбора между keep/discard.
"""
import logging
from event_agent.graph.state import CrawlState
from event_agent.tools.llm_classifier import classify_topic_pc

log = logging.getLogger(__name__)


def classify_topic_node(state: CrawlState) -> dict:
    record = state.get("current_record")
    if record is None or not record.is_valid:
        return {"topic_is_pc": False, "topic_reason": "invalid or missing extraction"}

    decision = classify_topic_pc(record.title, record.body_text)
    if decision is None:
        log.warning("PC topic classification unavailable (LLM down) for %s - discarding to be safe", record.url)
        return {"topic_is_pc": False, "topic_reason": "LLM unavailable"}

    log.info("Topic check: %s -> %s | %s",
              "ABOUT PC" if decision.is_about_pc else "NOT about PC", record.url, decision.reason)
    return {"topic_is_pc": decision.is_about_pc, "topic_reason": decision.reason}
