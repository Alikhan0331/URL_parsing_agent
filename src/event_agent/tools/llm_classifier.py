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
_BATCH_SIZE = 10

_FEW_SHOT_EXAMPLES = """
Примеры правильной классификации (ориентируйся на них):

0: href="https://www.akorda.kz/ru/glava-gosudarstva-prinyal-ministra-ekologii-483750" image=False time=False ends_with_numeric_id=True text="Глава государства принял министра экологии и природных ресурсов Алибека Куантырова"
-> is_content_card=true, reason="Конкретное событие (кто, что сделал), URL заканчивается числовым ID"

1: href="https://www.akorda.kz/ru/legal_acts" image=False time=False ends_with_numeric_id=False text="Правовые акты"
-> is_content_card=false, reason="Общее название раздела сайта, нет числового ID, нет описания конкретного события"

2: href="https://www.ektu.kz/newsevents/dombra_kuni.aspx" image=False time=False ends_with_numeric_id=False text="Домбыра күні құтты болсын!"
-> is_content_card=true, reason="Поздравление - это отдельный пост из новостной ленты университета, валидный контент, даже без числового ID"

3: href="https://eotinish.kz/sendAppeal?orgId=77" image=False time=False ends_with_numeric_id=False text="Подать обращение"
-> is_content_card=false, reason="Ссылка на внешний сервис подачи обращений, а не на новость/статью"

4: href="https://www.akorda.kz/ru/executive_office/schedule" image=False time=False ends_with_numeric_id=False text="График приёма граждан"
-> is_content_card=false, reason="Служебная страница раздела сайта, не конкретная новость"
"""


class LinkDecision(BaseModel):
    index: int
    is_content_card: bool
    reason: str = Field(description="Краткое объяснение (1 фраза) ИМЕННО для этой ссылки, не повторяй чужие причины")


class ClassifiedLinks(BaseModel):
    decisions: List[LinkDecision]


def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=0.2)
    return _llm


def _save_debug_decisions(decisions: List[dict], page_hint: str) -> None:
    debug_dir = Path("output/debug")
    debug_dir.mkdir(parents=True, exist_ok=True)
    safe_hint = "".join(c if c.isalnum() else "_" for c in page_hint)[:80]
    path = debug_dir / f"llm_decisions_{safe_hint}.json"
    path.write_text(json.dumps(decisions, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("Saved LLM reasoning for this page to %s - open it to see WHY each link was accepted/rejected", path)


def _classify_batch(candidates: list[dict]) -> Optional[List[LinkDecision]]:
    listing = "\n".join(
        f'{c["index"]}: href="{c["href"]}" image={c["has_image"]} time={c["has_time"]} '
        f'ends_with_numeric_id={c["has_trailing_id"]} text="{c["text_preview"]}"'
        for c in candidates
    )

    prompt = (
        "Ниже приведён список ссылок со страницы сайта в формате "
        "'индекс: href=... image=... time=... ends_with_numeric_id=... text=...'.\n"
        "Для КАЖДОЙ ссылки реши, является ли она карточкой контента в списке "
        "(отдельная новость, объявление, поздравление, анонс мероприятия или статья - "
        "то есть отдельный пост из новостной ленты), или служебной/навигационной ссылкой "
        "(пункт меню сайта, раздел 'о нас'/'структура'/'документы', контакты, ссылка "
        "на внешний сервис, ссылка на другую страницу пагинации).\n"
        "Важно: поздравления, объявления и короткие новости - это ВАЛИДНЫЙ контент "
        "новостной ленты, их нужно принимать наравне с обычными новостями. Не отклоняй "
        "ссылку только потому, что это поздравление или короткое сообщение.\n"
        "Важная подсказка: у карточек контента URL часто заканчивается числовым ID или "
        "содержит осмысленный slug с описанием темы, а у разделов сайта/меню - обычно "
        "короткий общий путь.\n"
        + _FEW_SHOT_EXAMPLES +
        "\nПроанализируй каждую ссылку ИНДИВИДУАЛЬНО - не копируй одно и то же обоснование "
        "для разных ссылок, у каждой должна быть своя причина, основанная на её содержании.\n"
        "Верни решение по каждому индексу из списка НИЖЕ (не по примерам выше) с кратким "
        "индивидуальным обоснованием.\n\n" + listing
    )

    log.debug("LLM classification batch prompt:\n%s", prompt)

    try:
        llm = _get_llm().with_structured_output(ClassifiedLinks)
        result = llm.invoke(prompt)
        return result.decisions
    except Exception as e:
        log.error("LLM link classification failed (is Ollama running at %s?): %s",
                  settings.ollama_base_url, e)
        return None


def classify_links_with_llm(html: str, base_url: str, max_candidates: int = 60) -> Optional[List[str]]:
    """Fallback для сайтов, где структурная эвристика (img + заголовок) не сработала.

    Использует few-shot примеры (реальные решения с akorda.kz и ektu.kz) вместо
    fine-tuning модели - дешёвый и быстро редактируемый способ дать модели "контекст"
    о том, как выглядят правильные решения, без изменения весов модели.
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

    index_to_candidate = {c["index"]: c for c in candidates}
    debug_records = []
    accepted_hrefs = []
    any_batch_succeeded = False

    for start in range(0, len(candidates), _BATCH_SIZE):
        batch = candidates[start:start + _BATCH_SIZE]
        decisions = _classify_batch(batch)
        if decisions is None:
            continue
        any_batch_succeeded = True

        for decision in decisions:
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

    if not any_batch_succeeded:
        return None

    return list(dict.fromkeys(accepted_hrefs))
