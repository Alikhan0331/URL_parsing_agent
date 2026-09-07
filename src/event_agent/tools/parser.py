import logging
from urllib.parse import urljoin, urlparse

import trafilatura
from bs4 import BeautifulSoup

from event_agent.graph.state import EventRecord
from event_agent.tools.fetcher import fetch_html

log = logging.getLogger(__name__)

_NAV_TAGS = {"nav", "header", "footer", "aside"}
_NAV_HINTS = ("menu", "nav", "footer", "header", "sidebar", "breadcrumb", "topbar")


def _is_in_navigation(tag) -> bool:
    for parent in tag.parents:
        if getattr(parent, "name", None) in _NAV_TAGS:
            return True
        classes = " ".join(parent.get("class", [])) + " " + str(parent.get("id", ""))
        if any(hint in classes.lower() for hint in _NAV_HINTS):
            return True
    return False


def _list_root_path(base_url: str) -> str:
    """Возвращает корневой путь страницы списка без query-строки и без {n}-плейсхолдера.

    Пример: "https://qr-pib.kz/ru/post/?page={n}" -> "/ru/post/"
    """
    clean = base_url.split("?")[0]
    parsed = urlparse(clean)
    return parsed.path


def extract_list_links(html: str, base_url: str, list_root_path: str | None = None) -> list[str]:
    """Находит ссылки на карточки контента (мероприятия/статьи), исключая навигацию и сайт-вайд ссылки.

    Ключевое условие: ссылка на карточку должна лежать в том же разделе сайта, что и сама
    страница списка (например, если список на /ru/post/, то карточки — /ru/post/<id>),
    и не должна находиться внутри <nav>/<header>/<footer>/<aside> или похожих блоков.
    Это отсекает сайт-вайд ссылки вроде "О госзакупках" (/ru/p/2312) или биографии
    руководства (/ru/p/2299), которые технически повторяются на каждой странице сайта.
    """
    if list_root_path is None:
        list_root_path = _list_root_path(base_url)
    list_root_path = list_root_path.rstrip("/") + "/"

    soup = BeautifulSoup(html, "html.parser")
    candidates = []

    for a in soup.find_all("a", href=True):
        if _is_in_navigation(a):
            continue

        href = urljoin(base_url, a["href"])
        path = urlparse(href).path

        if not path.startswith(list_root_path):
            continue
        if path.rstrip("/") == list_root_path.rstrip("/"):
            continue

        text = a.get_text(strip=True)
        if a.find("img") or (text and len(text) > 15):
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
