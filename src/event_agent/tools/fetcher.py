import logging
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from event_agent.config import settings

log = logging.getLogger(__name__)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
def _fetch_with_httpx(url: str) -> str | None:
    resp = httpx.get(
        url,
        timeout=settings.request_timeout,
        headers={"User-Agent": settings.user_agent},
        follow_redirects=True,
    )
    resp.raise_for_status()
    return resp.text


def _fetch_with_browser(url: str) -> str | None:
    """Fallback для сайтов, которые рендерят контент через JavaScript."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=settings.user_agent)
            page.goto(url, wait_until="networkidle", timeout=settings.request_timeout * 1000)
            return page.content()
        finally:
            browser.close()


def fetch_html(url: str) -> str | None:
    """Скачивает HTML: сначала простым HTTP-запросом, при неудаче — headless-браузером."""
    try:
        html = _fetch_with_httpx(url)
        if html and len(html) > 1000:
            return html
        log.info("httpx response too small for %s, falling back to browser", url)
    except Exception as e:
        log.warning("httpx fetch failed for %s: %s", url, e)

    try:
        return _fetch_with_browser(url)
    except Exception as e:
        log.error("Browser fetch failed for %s: %s", url, e)
        return None
