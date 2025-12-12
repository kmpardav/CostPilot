import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1].parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_runtest_setup():
    # Ensure price cache is cleared between tests to avoid cross-test leakage
    try:
        from azure_cost_architect.pricing import cache as price_cache

        price_cache._price_cache_best.clear()
    except Exception:
        pass
