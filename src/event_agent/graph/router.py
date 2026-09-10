from langgraph.types import Send
from langgraph.graph import END
from event_agent.graph.state import CrawlState


def route_after_list_page(state: CrawlState):
    """Решает: fan-out по найденным карточкам, либо завершение обхода."""
    if state.get("stop") or not state.get("event_urls"):
        return END
    return [Send("extract_event", {"url": url}) for url in state["event_urls"]]


def route_after_topic_classification(state: CrawlState):
    """Условный edge: сохранять запись только если LLM подтвердила, что статья релевантна ПЦ."""
    return "keep_record" if state.get("topic_is_pc") else "discard_record"


def route_after_pagination(state: CrawlState):
    """Решает: продолжать пагинацию или остановиться.

    Останавливается, если:
    - list_page выставил last_page=True (инкрементальный режим: страница дальше
      содержит только уже обработанные ранее ссылки);
    - или достигнут max_pages (если задан).
    """
    if state.get("last_page"):
        return END
    if state["max_pages"] is not None and state["current_page"] > state["max_pages"]:
        return END
    return "list_page"
