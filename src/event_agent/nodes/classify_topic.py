"""Узел графа: определяет, релевантна ли извлечённая статья Президентскому
центру (ПЦ), включая случаи, когда ПЦ упомянут просто как локация. Результат
используется условным edge для выбора между keep_record и discard_record.
"""
import logging
from event_agent.graph.state import CrawlState
from event_agent.tools.llm_classifier import classify_topic_pc

log = logging.getLogger(__name__)


def classify_topic_node(state: CrawlState) -> dict:
    record = state.get("current_record")
    if record is None or not record.is_valid:
        return {"topic_is_pc": False, "topic_reason": "invalid or missing extraction", "topic_conclusive": False}

    decision = classify_topic_pc(record.title, record.body_text)
    if decision is None:
        log.warning("PC relevance classification unavailable (LLM down) for %s - discarding to be safe", record.url)
        return {"topic_is_pc": False, "topic_reason": "LLM unavailable", "topic_conclusive": False}

    log.info("Relevance check: %s -> %s | %s",
              "RELEVANT" if decision.is_relevant_to_pc else "NOT relevant", record.url, decision.reason)
    return {"topic_is_pc": decision.is_relevant_to_pc, "topic_reason": decision.reason, "topic_conclusive": True}
