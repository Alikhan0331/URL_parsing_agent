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
    """Рендерит страницу headless-браузером - нужно для сайтов, которые подгружают
    контент через JavaScript/API уже после первоначального ответа сервера."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(user_agent=settings.user_agent)
            page.goto(url, wait_until="networkidle", timeout=settings.request_timeout * 1000)
            return page.content()
        finally:
            browser.close()


def fetch_html(url: str, force_browser: bool = False) -> str | None:
    """Скачивает HTML.

    По умолчанию сначала пробует обычный HTTP-запрос (быстро, дешево), и только если
    он не сработал (маленький ответ / ошибка) - переключается на headless-браузер.
    Если force_browser=True, браузер используется сразу - нужно для страниц, где
    обычный HTTP-запрос возвращает JS-"скелет" без реальных данных (SPA/CSR-сайты).
    """
    if not force_browser:
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
