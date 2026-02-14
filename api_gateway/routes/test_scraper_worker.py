import inspect
import types

import scraper_worker as sw

# Avoid real sleeps during tests to make them fast and deterministic
sw.time.sleep = lambda _sec: None


def test_start_driver_signature_no_duplicate():
    sig = inspect.signature(sw.start_driver)
    params = list(sig.parameters.keys())
    # Ensure 'proxy' was removed from start_driver signature
    assert 'proxy' not in params


def test_extract_link_from_page():
    html = '<html><body><div class="sCXXQd"><a href="https://target.example/product/123">Buy</a></div></body></html>'
    href = sw.extract_link_from_page(html)
    assert href == 'https://target.example/product/123'


class DummyDriver:
    def __init__(self, html):
        self.page_source = html
        self.scripts = []
        self.got_url = None

    def get(self, url):
        self.got_url = url

    def execute_script(self, script):
        self.scripts.append(script)

    def find_element(self, by, value):
        # Simulate element not found to keep human_scroll_and_pause's mouse move in try/except
        raise Exception("not implemented in dummy")

    def quit(self):
        pass


def test_process_item_finds_href():
    html = '<html><body><div class="sCXXQd"><a href="https://target.example/product/456">Buy</a></div></body></html>'
    driver = DummyDriver(html)
    item = {'position': 1, 'link': 'http://example.com'}
    href, blocked = sw.process_item(driver, item)
    assert href == 'https://target.example/product/456'
    assert blocked is False


def test_fetch_serpapi_product_link(monkeypatch):
    # Mock requests.get to return a fake JSON containing shopping_results with link
    class DummyResp:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return

        def json(self):
            return self._data

    sample_json = {
        'shopping_results': [
            {'link': 'https://example.com/product/123'}
        ]
    }

    def fake_get(url, timeout=0):
        return DummyResp(sample_json)

    monkeypatch.setattr(sw.requests, 'get', fake_get)
    item = {'serpapi_immersive_product_api': 'https://serpapi.com/fake?token=abc'}
    link = sw.fetch_serpapi_product_link(item, 'DUMMYKEY')
    assert link == 'https://example.com/product/123'

    # If shopping_results contains only images, we should ignore them and return None
    sample_json2 = {
        'shopping_results': [
            {'link': 'https://encrypted-tbn2.gstatic.com/someimage.jpg'},
            {'link': 'https://m.media-amazon.com/images/I/61iC7wjfK2L.jpg'}
        ]
    }

    def fake_get2(url, timeout=0):
        return DummyResp(sample_json2)

    monkeypatch.setattr(sw.requests, 'get', fake_get2)
    link2 = sw.fetch_serpapi_product_link(item, 'DUMMYKEY')
    assert link2 is None


def test_page_shows_block_detects_traffic_message():
    driver = DummyDriver('<html>Our systems have detected unusual traffic from your computer network</html>')
    assert sw.page_shows_block(driver) is True


if __name__ == '__main__':
    # Simple runner to avoid external test frameworks in CI-less environments
    tests = [
        test_start_driver_signature_no_duplicate,
        test_extract_link_from_page,
        test_process_item_finds_href,
        test_page_shows_block_detects_traffic_message,
    ]
    for t in tests:
        try:
            t()
            print(f"{t.__name__}: OK")
        except AssertionError as e:
            print(f"{t.__name__}: FAILED - {e}")
            raise
    print("All tests passed")
