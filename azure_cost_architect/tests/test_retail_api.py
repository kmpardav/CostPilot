import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from azure_cost_architect.pricing import retail_api


def test_fetch_all_for_service_sanitizes_top(monkeypatch):
    requested_urls = []

    class DummyResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    class DummyClient:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def get(self, url):
            requested_urls.append(url)
            self.calls += 1
            if self.calls == 1:
                return DummyResponse(
                    {
                        "Items": [{"skuName": "first"}],
                        "NextPageLink": "https://example.com/api?$top=-1000&$skip=1",
                    }
                )
            return DummyResponse({"Items": [{"skuName": "second"}], "NextPageLink": ""})

        def close(self):
            return None

    monkeypatch.setattr(retail_api, "httpx", SimpleNamespace(Client=DummyClient, Timeout=lambda *a, **k: None))

    items = retail_api.fetch_all_for_service(
        service_name="Virtual Machines", region="", currency="USD"
    )

    assert len(items) == 2
    assert len(requested_urls) == 2

    second_request = requested_urls[1]
    parsed = urlparse(second_request)
    qs = parse_qs(parsed.query)
    assert "$top" in qs
    assert int(qs["$top"][0]) >= 1
    assert int(qs["$top"][0]) <= 1000
    assert qs.get("currencyCode") == ["USD"]
