"""Общие вспомогательные функции для анализа DOM, используемые и структурной
эвристикой (parser.py), и LLM-классификатором (llm_classifier.py)."""

_NAV_TAGS = {"nav", "header", "footer", "aside"}
_NAV_HINTS = ("menu", "nav", "footer", "header", "sidebar", "breadcrumb", "topbar")


def is_in_navigation(tag) -> bool:
    """Проверяет, лежит ли тег внутри навигационного/служебного блока страницы."""
    for parent in tag.parents:
        if getattr(parent, "name", None) in _NAV_TAGS:
            return True
        classes = " ".join(parent.get("class", [])) + " " + str(parent.get("id", ""))
        if any(hint in classes.lower() for hint in _NAV_HINTS):
            return True
    return False
