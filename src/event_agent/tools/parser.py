import logging
from collections import Counter
from urllib.parse import urljoin

import trafilatura
from bs4 import BeautifulSoup

from event_agent.graph.state import EventRecord
from event_agent.tools.fetcher import fetch_html

log = logging.getLogger(__name__)


def extract_list_links(html: str, base_url: str) -> list[str]:
    """Находит ссылки на карточки мероприятий без знания конкретной вёрстки сайта.

    Эвристика: карточки почти всегда содержат картинку или заметный по длине текст,
    и почти всегда имеют одинаковый по структуре путь (/ru/post/123, /ru/post/124, ...).
    """
    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if a.find("img") or (text and len(text) > 15):
            candidates.append(urljoin(base_url, a["href"]))

    if not candidates:
        return []

    patterns = Counter("/".join(c.split("/")[:4]) for c in candidates)
    main_pattern, _ = patterns.most_common(1)[0]

    seen = set()
    result = []
    for c in candidates:
        if c.startswith(main_pattern) and c not in seen:
            seen.add(c)
            result.append(c)
    return result


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
