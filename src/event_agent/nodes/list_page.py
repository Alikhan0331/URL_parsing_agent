import logging
from pathlib import Path

from event_agent.config import settings
from event_agent.graph.state import CrawlState
from event_agent.tools.fetcher import fetch_html
from event_agent.tools.parser import extract_list_links
from event_agent.tools.llm_classifier import classify_links_with_llm, verify_candidates_with_llm

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

    if links and settings.llm_verify_structural:
        log.info("Verifying %d structurally-matched link(s) on page %d with LLM", len(links), state["current_page"])
        verified = verify_candidates_with_llm(html, url, links)
        if verified is not None:
            rejected = set(links) - set(verified)
            if rejected:
                log.info(
                    "LLM verification rejected %d structurally-matched link(s) on page %d "
                    "(same DOM shape - img+heading - but different meaning): %s",
                    len(rejected), state["current_page"], sorted(rejected),
                )
            links = verified
        else:
            log.warning(
                "LLM verification unavailable (Ollama unreachable?) - keeping structurally-matched "
                "links unverified for this page"
            )

    if not links and settings.use_llm_fallback:
        log.info("Structural heuristic found nothing on %s, asking LLM to classify links", url)
        llm_links = classify_links_with_llm(html, url)
        if llm_links:
            log.info("LLM classified %d links as content cards on page %d", len(llm_links), state["current_page"])
            links = llm_links
        elif llm_links is None:
            log.warning("LLM fallback unavailable - check that Ollama is running and OLLAMA_MODEL is pulled")

    if not links:
        log.warning(
            "No event links found on %s (structural heuristic and LLM fallback both empty). "
            "Check output/debug/list_page_%d.html to inspect the actual markup.",
            url, state["current_page"],
        )
        return {"event_urls": [], "stop": True}

    previous_links = state.get("previous_links") or []
    if previous_links and set(links) == set(previous_links):
        log.warning(
            "Page %d returned the exact same links as the previous page - pagination via "
            "?page=N (or your URL template) likely doesn't work on this site (common on ASP.NET "
            "WebForms sites using __doPostBack, or single-page archives). Stopping crawl to avoid "
            "reprocessing the same content forever.",
            state["current_page"],
        )
        return {"event_urls": [], "stop": True}

    log.info("Found %d event links on page %d", len(links), state["current_page"])
    return {"event_urls": links, "previous_links": links, "stop": False}
