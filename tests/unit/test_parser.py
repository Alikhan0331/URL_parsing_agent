from event_agent.tools.parser import extract_list_links

SAMPLE_HTML = """
<html><body>
<nav><a href="/ru/about">О нас</a><a href="/ru/contacts">Контакты</a></nav>
<div class="list">
    <a href="/ru/post/101"><img src="/img/1.jpg"/>Мероприятие один длинное название</a>
    <a href="/ru/post/102"><img src="/img/2.jpg"/>Мероприятие два длинное название</a>
</div>
<footer><a href="/ru/privacy">Политика</a></footer>
</body></html>
"""


def test_extract_list_links_filters_navigation():
    links = extract_list_links(SAMPLE_HTML, "https://example.com")
    assert len(links) == 2
    assert all("/ru/post/" in link for link in links)
    assert not any("about" in link or "contacts" in link or "privacy" in link for link in links)
