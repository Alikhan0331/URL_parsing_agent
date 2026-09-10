from langgraph.graph import StateGraph, START, END

from event_agent.graph.state import CrawlState
from event_agent.graph.router import route_after_list_page, route_after_pagination
from event_agent.nodes.list_page import list_page_node
from event_agent.nodes.extract_event import extract_event_node
from event_agent.nodes.pagination import next_page_node


def build_graph():
    graph = StateGraph(CrawlState)

    graph.add_node("list_page", list_page_node)
    graph.add_node("extract_event", extract_event_node)
    graph.add_node("next_page", next_page_node)

    graph.add_edge(START, "list_page")
    graph.add_conditional_edges(
        "list_page",
        route_after_list_page,
        {"extract_event": "extract_event", END: END},
    )
    graph.add_edge("extract_event", "next_page")
    graph.add_conditional_edges(
        "next_page",
        route_after_pagination,
        {"list_page": "list_page", END: END},
    )

    return graph.compile()
