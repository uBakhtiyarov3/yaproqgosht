import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("BOT_TOKEN", "123456:TEST-token")
os.environ.setdefault("ADMIN_IDS", "1")

import pytest


@pytest.fixture(autouse=True)
def _no_network_maps(monkeypatch):
    """Testlarda Google Maps havolasini internet orqali ochmaslik."""
    from app import geo

    async def fake_resolve(url):
        return geo.parse_coords(url)

    monkeypatch.setattr(geo, "resolve_map_url", fake_resolve)
    monkeypatch.setattr(geo, "_last_fail", 0.0)
