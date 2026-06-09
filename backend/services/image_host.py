"""services/image_host.py — optional GitHub image host for report charts.

Uploads a report's price-trend PNG to a GitHub repo via the Contents API so the
generated Markdown can embed the chart as a public ``raw.githubusercontent.com``
URL. This makes a downloaded report self-contained (the image loads from GitHub
even offline from the backend's perspective — no static mount required).

Honest degradation (NEVER raises to the caller):
  - Missing config (no token / no repo) → ``upload_png`` returns ``None``.
  - Any HTTP / network / parse failure → returns ``None``.
  When ``None`` is returned the report embeds the local ``/reports/<file>.png``
  path instead (on-screen still works via the frontend image rewrite; offline
  download simply loses the image — an honest, non-fatal degradation).

Config (all OPTIONAL — absence must not fail startup; NOT in REQUIRED_KEYS):
  GITHUB_TOKEN          personal-access / fine-grained token with contents:write
  GITHUB_IMAGE_REPO     "owner/repo" the charts are committed to
  GITHUB_IMAGE_BRANCH   branch to commit to (default "report-assets")

Test seam:
  Module-level ``_client_factory`` hook (mirrors the news/sec fakes). Tests set
  ``image_host._client_factory = lambda: FakeClient(...)`` so no real GitHub
  traffic occurs. Alternatively pass ``client=`` to ``upload_png`` directly.
"""
from __future__ import annotations

import base64
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Test seam: a module-level factory returning an httpx-like client.
# Tests override this to inject a fake (never hits real GitHub).
# ---------------------------------------------------------------------------

_client_factory: Any = None    # None → build a real httpx.Client


def _make_client() -> Any:
    if _client_factory is not None:
        return _client_factory()
    import httpx
    return httpx.Client(timeout=15.0)


def _github_config(settings) -> Optional[tuple[str, str, str]]:
    """Return (token, repo, branch) when fully configured, else None."""
    token = (getattr(settings, "github_token", None) or "").strip()
    repo = (getattr(settings, "github_image_repo", None) or "").strip()
    branch = (getattr(settings, "github_image_branch", None) or "").strip() or "report-assets"
    if not token or not repo:
        return None
    return token, repo, branch


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _ensure_branch(client: Any, repo: str, branch: str, headers: dict[str, str]) -> None:
    """Create ``branch`` from the repo default branch if it does not exist.

    Best-effort: if the branch already exists, or anything fails, we leave it to
    the subsequent PUT to surface a real error (which the caller turns into None).
    """
    # Does the branch ref already exist?
    resp = client.get(
        f"https://api.github.com/repos/{repo}/git/ref/heads/{branch}",
        headers=headers,
    )
    if resp.status_code == 200:
        return

    # Resolve the repo's default branch and its head sha.
    repo_resp = client.get(f"https://api.github.com/repos/{repo}", headers=headers)
    repo_resp.raise_for_status()
    default_branch = repo_resp.json().get("default_branch", "main")

    ref_resp = client.get(
        f"https://api.github.com/repos/{repo}/git/ref/heads/{default_branch}",
        headers=headers,
    )
    ref_resp.raise_for_status()
    base_sha = ref_resp.json()["object"]["sha"]

    client.post(
        f"https://api.github.com/repos/{repo}/git/refs",
        headers=headers,
        json={"ref": f"refs/heads/{branch}", "sha": base_sha},
    )


def upload_png(data: bytes, dest_filename: str, settings, *, client: Any = None) -> Optional[str]:
    """Upload a PNG to GitHub and return its public raw URL, or None.

    Parameters
    ----------
    data:
        Raw PNG bytes.
    dest_filename:
        Unique destination filename (the existing per-report chart hash filename
        is already unique, so collisions should not happen). Committed under
        ``report-charts/<dest_filename>`` on the configured branch.
    settings:
        A ``config.Settings`` instance (read for github_token / github_image_repo
        / github_image_branch).
    client:
        Optional httpx-like client (test seam). When omitted, ``_make_client()``
        is used (which honours the module-level ``_client_factory`` hook).

    Returns
    -------
    The public raw URL on success, otherwise ``None``. NEVER raises.
    """
    cfg = _github_config(settings)
    if cfg is None:
        return None
    token, repo, branch = cfg

    owns_client = client is None
    try:
        if client is None:
            client = _make_client()
    except Exception:  # noqa: BLE001 — client construction must never raise out
        return None

    path = f"report-charts/{dest_filename}"
    raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
    headers = _headers(token)

    try:
        # Create the branch first if necessary (degrade silently on failure).
        try:
            _ensure_branch(client, repo, branch, headers)
        except Exception:  # noqa: BLE001 — branch creation is best-effort
            pass

        resp = client.put(
            f"https://api.github.com/repos/{repo}/contents/{path}",
            headers=headers,
            json={
                "message": f"Add report chart {dest_filename}",
                "content": base64.b64encode(data).decode("ascii"),
                "branch": branch,
            },
        )

        # Already exists → treat as success (unique filenames make this benign).
        if resp.status_code in (409, 422):
            return raw_url

        if resp.status_code not in (200, 201):
            return None

        # Prefer the URL GitHub reports; fall back to the constructed raw URL.
        try:
            content = resp.json().get("content") or {}
            download_url = content.get("download_url")
            if download_url:
                return download_url
        except Exception:  # noqa: BLE001
            pass
        return raw_url
    except Exception:  # noqa: BLE001 — any failure degrades to None
        return None
    finally:
        if owns_client:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
