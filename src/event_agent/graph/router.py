from langgraph.types import Send
from langgraph.graph import END
from event_agent.graph.state import CrawlState


def route_after_list_page(state: CrawlState):
    """Решает: fan-out по найденным карточкам, либо завершение обхода."""
    if state.get("stop") or not state.get("event_urls"):
        return END
    return [Send("extract_event", {"url": url}) for url in state["event_urls"]]


def route_after_pagination(state: CrawlState):
    """Решает: продолжать пагинацию или остановиться.

    Если max_pages задан (не None) - останавливаемся по достижению лимита.
    Если max_pages is None - обход продолжается неограниченно, пока list_page
    сам не выставит stop=True (пустая страница / нет карточек).
    """
    if state["max_pages"] is not None and state["current_page"] > state["max_pages"]:
        return END
    return "list_page"
