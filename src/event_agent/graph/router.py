from langgraph.types import Send
from langgraph.graph import END
from event_agent.graph.state import CrawlState


def route_after_list_page(state: CrawlState):
    """Решает: fan-out по найденным карточкам, либо завершение обхода.

    conn/site_name прокидываются в каждую Send-задачу явно (см. EventTask) - общие
    (не-Annotated) поля state нельзя писать параллельно из нескольких Send-веток.
    """
    if state.get("stop") or not state.get("event_urls"):
        return END
    conn = state.get("conn")
    site_name = state.get("site_name")
    return [
        Send("extract_event", {"url": url, "conn": conn, "site_name": site_name})
        for url in state["event_urls"]
    ]


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
