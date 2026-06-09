"""tests/test_image_host.py — services/image_host.upload_png (offline).

The GitHub image host is exercised entirely through a FAKE httpx-like client so
NO real GitHub traffic ever occurs. Covers:
  - missing config (no token / no repo) → None, client never built
  - happy path → PUT contents, returns the raw URL (or content.download_url)
  - branch auto-creation when the target branch ref is absent
  - "already exists" (409/422) treated as success
  - any HTTP failure → None (never raises)
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import services.image_host as image_host


# ---------------------------------------------------------------------------
# Fake httpx-like client
# ---------------------------------------------------------------------------


class _Resp:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """Programmable fake. ``put_status`` controls the contents PUT result;
    ``branch_exists`` controls whether the branch ref is found."""

    def __init__(self, *, put_status: int = 201, branch_exists: bool = True,
                 put_payload: Any = None) -> None:
        self.put_status = put_status
        self.branch_exists = branch_exists
        self.put_payload = put_payload
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    def get(self, url: str, headers=None) -> _Resp:
        self.calls.append(("GET", url))
        if url.endswith("/git/ref/heads/report-assets"):
            # The target-branch existence probe.
            return _Resp(200, {"object": {"sha": "x"}}) if self.branch_exists else _Resp(404)
        if "/git/ref/heads/" in url:
            # The default-branch (base) ref lookup → always resolvable.
            return _Resp(200, {"object": {"sha": "basesha"}})
        # repo metadata
        return _Resp(200, {"default_branch": "main"})

    def post(self, url: str, headers=None, json=None) -> _Resp:
        self.calls.append(("POST", url))
        return _Resp(201, {})

    def put(self, url: str, headers=None, json=None) -> _Resp:
        self.calls.append(("PUT", url))
        return _Resp(self.put_status, self.put_payload)

    def close(self) -> None:
        self.closed = True


def _settings(**over) -> SimpleNamespace:
    base = dict(github_token="tok", github_image_repo="owner/repo",
                github_image_branch="report-assets")
    base.update(over)
    return SimpleNamespace(**base)


def test_missing_config_returns_none_without_client(monkeypatch):
    """No token / no repo → None and the real client is never constructed."""
    built = {"n": 0}

    def _boom():
        built["n"] += 1
        raise AssertionError("client must not be built when unconfigured")

    monkeypatch.setattr(image_host, "_client_factory", _boom)

    assert image_host.upload_png(b"PNG", "x.png", _settings(github_token=None)) is None
    assert image_host.upload_png(b"PNG", "x.png", _settings(github_image_repo=None)) is None
    assert built["n"] == 0


def test_happy_path_returns_raw_url():
    fake = _FakeClient(put_status=201, branch_exists=True)
    url = image_host.upload_png(b"PNG", "abc_MSFT.png", _settings(), client=fake)
    assert url == (
        "https://raw.githubusercontent.com/owner/repo/report-assets/"
        "report-charts/abc_MSFT.png"
    )
    # The contents PUT was issued.
    assert any(m == "PUT" for m, _ in fake.calls)
    # Caller-supplied client is NOT closed by upload_png.
    assert fake.closed is False


def test_prefers_content_download_url_when_present():
    payload = {"content": {"download_url": "https://raw.example/dl.png"}}
    fake = _FakeClient(put_status=201, branch_exists=True, put_payload=payload)
    url = image_host.upload_png(b"PNG", "x.png", _settings(), client=fake)
    assert url == "https://raw.example/dl.png"


def test_creates_branch_when_absent():
    fake = _FakeClient(put_status=201, branch_exists=False)
    url = image_host.upload_png(b"PNG", "x.png", _settings(), client=fake)
    assert url is not None
    # A POST to create the new ref was issued.
    assert any(m == "POST" and u.endswith("/git/refs") for m, u in fake.calls)


def test_already_exists_is_success():
    for status in (409, 422):
        fake = _FakeClient(put_status=status, branch_exists=True)
        url = image_host.upload_png(b"PNG", "x.png", _settings(), client=fake)
        assert url == (
            "https://raw.githubusercontent.com/owner/repo/report-assets/"
            "report-charts/x.png"
        )


def test_http_failure_returns_none():
    fake = _FakeClient(put_status=500, branch_exists=True)
    assert image_host.upload_png(b"PNG", "x.png", _settings(), client=fake) is None


def test_client_factory_used_and_closed(monkeypatch):
    """When no client is passed, the module factory builds one and it is closed."""
    fake = _FakeClient(put_status=201, branch_exists=True)
    monkeypatch.setattr(image_host, "_client_factory", lambda: fake)
    url = image_host.upload_png(b"PNG", "x.png", _settings())
    assert url is not None
    assert fake.closed is True
