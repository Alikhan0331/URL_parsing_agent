from event_agent.graph.state import CrawlState


def next_page_node(state: CrawlState) -> dict:
    return {"current_page": state["current_page"] + 1}
