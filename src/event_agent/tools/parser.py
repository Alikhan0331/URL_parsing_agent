import logging
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup

from event_agent.graph.state import EventRecord
from event_agent.tools.fetcher import fetch_html
from event_agent.tools.dom_utils import is_in_navigation

log = logging.getLogger(__name__)

_HEADING_TAGS = ("h1", "h2", "h3", "h4", "h5")


def _looks_like_card(a) -> bool:
    """Определяет, похожа ли ссылка на карточку контента (мероприятие/статья/новость).

    Универсальный признак вместо привязки к конкретному URL-паттерну: карточка почти
    всегда содержит картинку + заголовок (h1-h5), часто вместе с датой (<time>) и
    коротким анонсом (<p>). Простые текстовые ссылки в меню/подвале такой структуры
    не имеют, даже если у них похожий по формату URL (как /ru/p/<id> на некоторых сайтах,
    где и мероприятия, и служебные страницы используют один и тот же путь).
    """
    has_img = a.find("img") is not None
    heading = a.find(_HEADING_TAGS)
    heading_ok = bool(heading and len(heading.get_text(strip=True)) > 5)
    return has_img and heading_ok


def extract_list_links(html: str, base_url: str, list_root_path: str | None = None) -> list[str]:
    """Находит ссылки на карточки контента по структуре разметки, а не по URL.

    list_root_path (опционально) - дополнительный фильтр: если задан, ссылка должна
    ещё и начинаться с этого пути. Полезно, если на сайте карточки действительно лежат
    в отдельном разделе. Если не задан - фильтрация идёт только по структуре карточки.
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for a in soup.find_all("a", href=True):
        if is_in_navigation(a):
            continue
        if not _looks_like_card(a):
            continue

        href = urljoin(base_url, a["href"])
        if list_root_path and not href.startswith(urljoin(base_url, list_root_path)):
            continue

        candidates.append(href)

    return list(dict.fromkeys(candidates))


def extract_event(url: str) -> EventRecord:
    html = fetch_html(url)
    if not html:
        return EventRecord(url=url, is_valid=False)

    soup = BeautifulSoup(html, "html.parser")

    title = None
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content"):
        title = og_title["content"].strip()
    elif soup.find("h1"):
        title = soup.find("h1").get_text(strip=True)

    body_text = trafilatura.extract(html, include_images=False, favor_recall=True)

    images = []
    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        images.append(urljoin(url, og_image["content"]))

    for img in soup.select("article img, .content img, .post img, .entry-content img"):
        src = img.get("src") or img.get("data-src")
        if src:
            images.append(urljoin(url, src))

    images = list(dict.fromkeys(images))
    is_valid = bool(title and body_text and len(body_text) > 50)

    if not is_valid:
        log.warning("Low-quality extraction for %s (title=%s, text_len=%s)",
                     url, bool(title), len(body_text or ""))

    return EventRecord(url=url, title=title, body_text=body_text, images=images, is_valid=is_valid)
