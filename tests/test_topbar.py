def test_page_links_scroll_in_their_own_strip(client):
    # Issue #238: with many pages on, the links pushed Sign out and Settings off the screen.
    page = client.get("/").get_data(as_text=True)
    nav = page[page.index('<nav class="topbar-nav"'):page.index('</nav>', page.index('<nav class="topbar-nav"'))]
    assert 'href="/problems"' in nav and 'id="btn-refresh-all"' in nav
    assert 'href="/settings"' not in nav and 'action="/logout"' not in nav
    assert 'href="/settings"' in page
