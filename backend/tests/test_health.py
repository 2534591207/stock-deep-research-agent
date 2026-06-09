"""tests/test_health.py — T0.3: GET /health → 200 {ok: true}.

Health endpoint must always return 200 regardless of key configuration,
because it is decoupled from agent / require_keys.
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# We patch require_keys so the lifespan startup does not raise during import
# in environments where .env keys may be absent.
# ---------------------------------------------------------------------------

@pytest.fixture()
def client():
    """TestClient with startup require_keys patched out."""
    with patch("app.require_keys", return_value=None):
        from app import app
        with TestClient(app, raise_server_exceptions=True) as c:
            yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_returns_ok_true(self, client):
        response = client.get("/health")
        data = response.json()
        assert data == {"ok": True}

    def test_health_ok_field_is_bool_true(self, client):
        response = client.get("/health")
        data = response.json()
        assert data.get("ok") is True

    def test_health_content_type_json(self, client):
        response = client.get("/health")
        assert "application/json" in response.headers.get("content-type", "")
