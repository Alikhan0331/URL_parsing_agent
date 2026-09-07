import json
import logging
import re
from pathlib import Path
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from langchain_ollama import ChatOllama

from event_agent.config import settings
from event_agent.tools.dom_utils import is_in_navigation

log = logging.getLogger(__name__)

_llm = None
_TRAILING_ID_RE = re.compile(r"-\d{3,}/?$")


class LinkDecision(BaseModel):
    index: int
    is_content_card: bool
    reason: str = Field(description="Краткое объяснение (1 фраза), почему ссылка отнесена к этой категории")


class ClassifiedLinks(BaseModel):
    decisions: List[LinkDecision]


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0)
    return _llm


def _save_debug_decisions(decisions: List[dict], page_hint: str) -> None:
    debug_dir = Path("output/debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    safe_hint = "".join(c if c.isalnum() else "_" for c in page_hint)[:80]
    path = debug_dir / f"llm_decisions_{safe_hint}.json"
    path.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved LLM reasoning for this page to %s - open it to see WHY each link was accepted/rejected", path)


def classify_links_with_llm(html: str, base_url: str, max_candidates: int = 60) -> Optional[List[str]]:
    """Fallback для сайтов, где структурная эвристика (img + заголовок) не сработала.

    Модель смотрит на список ссылок страницы (текст, наличие картинки/времени, признак
    числового ID в конце URL) и решает, какие из них - карточки контента, а какие -
    служебные/навигационные ссылки. Кандидаты предварительно чистятся тем же фильтром
    is_in_navigation, что и в структурной эвристике.

    Модель обязана вернуть решение по КАЖДОЙ ссылке с кратким обоснованием (LinkDecision) -
    это и есть видимое "рассуждение" агента. Полный список решений сохраняется в
    output/debug/llm_decisions_<page>.json, чтобы можно было посмотреть, почему модель приняла
    или отвергла конкретную ссылку.
    """
    soup = BeautifulSoup(html, "html.parser")
    anchors = soup.find_all("a", href=True)

    candidates = []
    for i, a in enumerate(anchors):
        if is_in_navigation(a):
            continue

        text = a.get_text(" ", strip=True)
        if not text or len(text) < 10:
            continue

        href = urljoin(base_url, a["href"])
        candidates.append({
            "index": i,
            "href": href,
            "has_image": a.find("img") is not None,
            "has_time": a.find("time") is not None,
            "has_trailing_id": bool(_TRAILING_ID_RE.search(href)),
            "text_preview": text[:150],
        })
        if len(candidates) >= max_candidates:
            break

    if not candidates:
        return []

    listing = "\n".join(
        f'{c["index"]}: href="{c["href"]}" image={c["has_image"]} time={c["has_time"]} '
        f'ends_with_numeric_id={c["has_trailing_id"]} text="{c["text_preview"]}"'
        for c in candidates
    )

    prompt = (
        "Ниже приведён список ссылок со страницы сайта в формате "
        "'индекс: href=... image=... time=... ends_with_numeric_id=... text=...'.\n"
        "Для КАЖДОЙ ссылки реши, является ли она карточкой контента в списке "
        "(анонс мероприятия, новости или статьи), или служебной/навигационной ссылкой "
        "(пункт меню сайта, раздел 'о нас'/'структура'/'документы', контакты, ссылка "
        "на внешний сервис, ссылка на другую страницу пагинации).\n"
        "Важная подсказка: у карточек контента URL почти всегда заканчивается числовым ID "
        "(ends_with_numeric_id=True), а у разделов сайта/меню - нет. Заголовок карточки контента "
        "обычно описывает конкретное событие или новость (кто, что сделал, когда), а не общее "
        "название раздела сайта.\n"
        "Верни решение по каждому индексу из списка с кратким обоснованием.\n\n" + listing
    )

    log.debug("LLM classification prompt for %s:\n%s", base_url, prompt)

    try:
        llm = _get_llm().with_structured_output(ClassifiedLinks)
        result = llm.invoke(prompt)
    except Exception as e:
        log.error("LLM link classification failed (is Ollama running at %s?): %s",
                  settings.ollama_base_url, e)
        return None

    index_to_candidate = {c["index"]: c for c in candidates}
    debug_records = []
    accepted_hrefs = []

    for decision in result.decisions:
        candidate = index_to_candidate.get(decision.index)
        if candidate is None:
            continue
        record = {
            "href": candidate["href"],
            "text_preview": candidate["text_preview"],
            "is_content_card": decision.is_content_card,
            "reason": decision.reason,
        }
        debug_records.append(record)
        log.info(
            "LLM decision: %s -> %s (%s) | %s",
            "ACCEPT" if decision.is_content_card else "reject",
            candidate["href"],
            candidate["text_preview"][:60],
            decision.reason,
        )
        if decision.is_content_card:
            accepted_hrefs.append(candidate["href"])

    _save_debug_decisions(debug_records, base_url)

    return list(dict.fromkeys(accepted_hrefs))
