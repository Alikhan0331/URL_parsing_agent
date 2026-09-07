from event_agent.tools.parser import extract_list_links

SAMPLE_HTML = """
<html><body>
<nav><a href="/ru/about">О нас</a><a href="/ru/p/2312">Госзакупки</a></nav>
<div class="list">
    <a href="/ru/post/101"><img src="/img/1.jpg"/>Мероприятие один длинное название</a>
    <a href="/ru/post/102"><img src="/img/2.jpg"/>Мероприятие два длинное название</a>
</div>
<footer><a href="/ru/p/2299">Управляющий делами</a></footer>
</body></html>
"""


def test_extract_list_links_filters_navigation_and_sitewide_pages():
    links = extract_list_links(SAMPLE_HTML, "https://qr-pib.kz/ru/post/?page=1")
    assert len(links) == 2
    assert all("/ru/post/" in link for link in links)
    assert not any("/ru/p/" in link for link in links)


def test_extract_list_links_respects_explicit_root_path():
    links = extract_list_links(SAMPLE_HTML, "https://qr-pib.kz/ru/post/?page=1", list_root_path="/ru/post/")
    assert len(links) == 2
