import logging
from event_agent.graph.state import CrawlState
from event_agent.tools.fetcher import fetch_html
from event_agent.tools.parser import extract_list_links

log = logging.getLogger(__name__)


def list_page_node(state: CrawlState) -> dict:
    url = state["base_list_url"].format(n=state["current_page"])
    log.info("Fetching list page: %s", url)

    html = fetch_html(url)
    if not html:
        log.warning("Empty response for %s, stopping crawl", url)
        return {"event_urls": [], "stop": True}

    links = extract_list_links(html, url, list_root_path=state.get("list_root_path"))
    if not links:
        log.info("No event links found on %s, stopping crawl", url)
        return {"event_urls": [], "stop": True}

    log.info("Found %d event links on page %d", len(links), state["current_page"])
    return {"event_urls": links, "stop": False}
