import sys
import types
# Provide minimal placeholders for optional heavy dependencies that may not be installed in test env
sys.modules.setdefault('pika', types.SimpleNamespace())
# stub jwt used by worker for token generation
if 'jwt' not in sys.modules:
    class DummyJWT:
        def encode(self, payload, key, algorithm):
            return 'dummy-token'
    sys.modules['jwt'] = DummyJWT()
# stub database used by worker
if 'database' not in sys.modules:
    class DummyDBModule:
        class AuthDatabase:
            def __init__(self):
                pass
            def setup_database(self):
                return
            def register_user(self, **kwargs):
                return {'status': 'SUCCESS'}
            def verify_user(self, **kwargs):
                return {'status': 'SUCCESS'}
            def save_otp(self, email, otp):
                return {'status': 'SUCCESS'}
            def reset_password_with_otp(self, email, otp, new_password):
                return {'status': 'SUCCESS'}
    sys.modules['database'] = DummyDBModule()
import worker as w
import scraper_worker as sw

class DummyItem(dict):
    pass


def test_search_google_shopping_fastpath(monkeypatch=None):
    # Allow running without pytest by providing a tiny monkeypatch fallback
    if monkeypatch is None:
        class SimpleMonkey:
            @staticmethod
            def setattr(target, name=None, val=None):
                import sys as _sys
                # Support two calling styles: ("module.attr", value) or (module, "attr", value)
                if isinstance(target, str):
                    if val is None:
                        val = name
                    module_path, attr = target.rsplit('.', 1)
                    mod = _sys.modules.get(module_path) or __import__(module_path, fromlist=[attr])
                    setattr(mod, attr, val)
                else:
                    setattr(target, name, val)
        monkeypatch = SimpleMonkey()

    # Prepare a single shopping result that contains only google product link
    shopping_data = [
        {
            'position': 1,
            'title': 'Test Product',
            'link': None,
            'product_link': 'https://www.google.com/search?ibp=oshop&q=Test',
            'price': '\u20b9100',
            'rating': 4.5,
            'reviews': 10,
            'thumbnail': 'https://example.com/thumb.jpg',
            'source': 'TestSource'
        }
    ]

    # Monkeypatch GoogleSearch to return our shopping_data
    class DummySearch:
        def __init__(self, params):
            pass
        def get_dict(self):
            return {'shopping_results': shopping_data}

    monkeypatch.setattr('worker.GoogleSearch', DummySearch)

    # Monkeypatch scrapper fast-path to return a product URL
    def fake_fetch(item, api_key):
        return 'https://example.com/product/123'

    # Patch the function in the worker module (worker imported it at module import time)
    monkeypatch.setattr('worker.fetch_serpapi_product_link', fake_fetch)

    res = w.search_google_shopping('test')
    assert res['status'] == 'SUCCESS'
    data = res['data']
    assert len(data) == 1
    assert data[0]['buy_link'] == 'https://example.com/product/123'


if __name__ == '__main__':
    test_search_google_shopping_fastpath()
    print('test_search_google_shopping_fastpath: OK')
