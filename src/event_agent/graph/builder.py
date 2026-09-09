from langgraph.graph import StateGraph, START, END

from event_agent.graph.state import CrawlState
from event_agent.graph.router import (
    route_after_list_page,
    route_after_pagination,
    route_after_topic_classification,
)
from event_agent.nodes.list_page import list_page_node
from event_agent.nodes.extract_event import extract_event_node
from event_agent.nodes.classify_topic import classify_topic_node
from event_agent.nodes.topic_gate import keep_record_node, discard_record_node
from event_agent.nodes.pagination import next_page_node


def build_graph():
    graph = StateGraph(CrawlState)

    graph.add_node("list_page", list_page_node)
    graph.add_node("extract_event", extract_event_node)
    graph.add_node("classify_topic", classify_topic_node)
    graph.add_node("keep_record", keep_record_node)
    graph.add_node("discard_record", discard_record_node)
    graph.add_node("next_page", next_page_node)

    graph.add_edge(START, "list_page")
    graph.add_conditional_edges(
        "list_page",
        route_after_list_page,
        {"extract_event": "extract_event", END: END},
    )
    graph.add_edge("extract_event", "classify_topic")
    graph.add_conditional_edges(
        "classify_topic",
        route_after_topic_classification,
        {"keep_record": "keep_record", "discard_record": "discard_record"},
    )
    graph.add_edge("keep_record", "next_page")
    graph.add_edge("discard_record", "next_page")
    graph.add_conditional_edges(
        "next_page",
        route_after_pagination,
        {"list_page": "list_page", END: END},
    )

    return graph.compile()
