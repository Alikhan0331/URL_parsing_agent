import logging
from pathlib import Path

from event_agent.graph.state import CrawlState
from event_agent.tools.fetcher import fetch_html
from event_agent.tools.parser import extract_list_links

log = logging.getLogger(__name__)


def _save_debug_html(html: str, page_num: int) -> None:
    debug_dir = Path("output/debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / f"list_page_{page_num}.html").write_text(html, encoding="utf-8")


def list_page_node(state: CrawlState) -> dict:
    url = state["base_list_url"].format(n=state["current_page"])
    log.info("Fetching list page: %s", url)

    html = fetch_html(url)
    links = extract_list_links(html, url, list_root_path=state.get("list_root_path")) if html else []

    if not links:
        log.info("No links found via plain HTTP fetch, retrying %s with headless browser", url)
        html = fetch_html(url, force_browser=True)
        links = extract_list_links(html, url, list_root_path=state.get("list_root_path")) if html else []

    if html:
        _save_debug_html(html, state["current_page"])

    if not html:
        log.warning("Empty response for %s, stopping crawl", url)
        return {"event_urls": [], "stop": True}

    if not links:
        log.warning(
            "No event links found on %s even after browser fallback. "
            "Check output/debug/list_page_%d.html to inspect the actual markup, "
            "or pass an explicit --list-root-path.",
            url, state["current_page"],
        )
        return {"event_urls": [], "stop": True}

    log.info("Found %d event links on page %d", len(links), state["current_page"])
    return {"event_urls": links, "stop": False}
