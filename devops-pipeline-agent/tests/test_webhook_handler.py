"""
tests/test_webhook_handler.py

Tests for webhook_handler.py — covers:
  - Health endpoint
  - GitHub PR opened / synchronize events
  - GitHub push event
  - GitHub deployment_status event
  - GitLab MR opened event
  - GitLab push event
  - GitLab pipeline event
  - Signature verification (valid / invalid)
  - Unknown / ignored event types

Uses FastAPI's TestClient (synchronous) via httpx; no live network calls —
the risk API is mocked with unittest.mock.patch.
"""

import hashlib
import hmac
import json
import os
import pytest

from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

# ── App under test ──────────────────────────────────────────────────────────
os.environ.setdefault("WEBHOOK_SECRET", "")
os.environ.setdefault("RISK_API_URL", "http://mock-risk-api:8000")

from webhook_handler import app, verify_github_signature  # noqa: E402

client = TestClient(app, raise_server_exceptions=True)

# ── Helpers ─────────────────────────────────────────────────────────────────

MOCK_ASSESSMENT = {
    "score": 0.55,
    "recommendation": "review",
    "risk_factors": ["Production environment adds baseline risk"],
}


def _make_signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _github_headers(event: str, body: bytes, secret: str = "") -> dict:
    headers = {"X-GitHub-Event": event, "Content-Type": "application/json"}
    if secret:
        headers["X-Hub-Signature-256"] = _make_signature(secret, body)
    return headers


# ── Health ───────────────────────────────────────────────────────────────────

class TestHealth:
    def test_returns_ok(self):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "webhook_handler"


# ── GitHub webhook ───────────────────────────────────────────────────────────

class TestGitHubWebhook:
    PR_PAYLOAD = {
        "action": "opened",
        "pull_request": {
            "number": 42,
            "user": {"login": "alice"},
            "changed_files": 5,
            "additions": 120,
            "deletions": 30,
            "updated_at": "2026-09-29T10:00:00Z",
        },
        "repository": {"name": "auth-service"},
    }

    PUSH_PAYLOAD = {
        "ref": "refs/heads/dev",
        "pusher": {"name": "bob"},
        "repository": {"name": "auth-service"},
    }

    DEPLOY_PAYLOAD = {
        "deployment": {
            "id": 12345,
            "environment": "production",
            "sha": "abc1234567890",
            "creator": {"login": "alice"},
        },
        "deployment_status": {"state": "success"},
        "repository": {"name": "auth-service"},
    }

    def _post(self, event: str, payload: dict) -> "Response":
        body = json.dumps(payload).encode()
        return client.post(
            "/webhook/github",
            content=body,
            headers=_github_headers(event, body),
        )

    @patch("webhook_handler.call_risk_api", return_value=MOCK_ASSESSMENT)
    def test_pr_opened_is_assessed(self, mock_risk):
        resp = self._post("pull_request", self.PR_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "assessed"
        assert data["pr_number"] == 42
        assert data["risk_assessment"]["score"] == 0.55
        mock_risk.assert_called_once()

    @patch("webhook_handler.call_risk_api", return_value=MOCK_ASSESSMENT)
    def test_pr_synchronize_is_assessed(self, mock_risk):
        payload = dict(self.PR_PAYLOAD)
        payload["action"] = "synchronize"
        body = json.dumps(payload).encode()
        resp = client.post(
            "/webhook/github",
            content=body,
            headers=_github_headers("pull_request", body),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "assessed"

    @patch("webhook_handler.call_risk_api", return_value=MOCK_ASSESSMENT)
    def test_pr_closed_is_ignored(self, mock_risk):
        payload = dict(self.PR_PAYLOAD)
        payload["action"] = "closed"
        body = json.dumps(payload).encode()
        resp = client.post(
            "/webhook/github",
            content=body,
            headers=_github_headers("pull_request", body),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        mock_risk.assert_not_called()

    def test_push_event_is_recorded(self):
        resp = self._post("push", self.PUSH_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"
        assert data["branch"] == "dev"
        assert data["pusher"] == "bob"

    @patch("webhook_handler.httpx.post")
    def test_deployment_status_success_is_recorded(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200)
        resp = self._post("deployment_status", self.DEPLOY_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"
        assert data["outcome"] == "success"

    def test_unknown_event_is_ignored(self):
        resp = self._post("star", {"action": "created"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"


# ── Signature verification ────────────────────────────────────────────────────

class TestSignatureVerification:
    """Tests the verify_github_signature helper directly."""

    def test_valid_signature_returns_true(self):
        secret = "s3cr3t"
        payload = b'{"test": true}'
        sig = _make_signature(secret, payload)
        with patch.dict(os.environ, {"WEBHOOK_SECRET": secret}):
            import webhook_handler
            webhook_handler.WEBHOOK_SECRET = secret
            assert verify_github_signature(payload, sig) is True

    def test_invalid_signature_returns_false(self):
        import webhook_handler
        webhook_handler.WEBHOOK_SECRET = "s3cr3t"
        assert verify_github_signature(b"payload", "sha256=badhash") is False

    def test_empty_secret_skips_verification(self):
        import webhook_handler
        webhook_handler.WEBHOOK_SECRET = ""
        # When no secret is set, always returns True (dev mode)
        assert verify_github_signature(b"anything", "sha256=doesntmatter") is True

    def test_webhook_rejects_invalid_signature(self):
        """End-to-end: 401 when a secret is configured and signature is wrong."""
        import webhook_handler
        original_secret = webhook_handler.WEBHOOK_SECRET
        webhook_handler.WEBHOOK_SECRET = "configured_secret"
        try:
            payload = json.dumps({"action": "opened"}).encode()
            resp = client.post(
                "/webhook/github",
                content=payload,
                headers={
                    "X-GitHub-Event": "pull_request",
                    "X-Hub-Signature-256": "sha256=invalid",
                    "Content-Type": "application/json",
                },
            )
            assert resp.status_code == 401
        finally:
            webhook_handler.WEBHOOK_SECRET = original_secret


# ── GitLab webhook ────────────────────────────────────────────────────────────

class TestGitLabWebhook:
    MR_PAYLOAD = {
        "object_kind": "merge_request",
        "user": {"username": "charlie"},
        "project": {"name": "payment-service"},
        "object_attributes": {
            "iid": 7,
            "state": "opened",
            "changes_count": 3,
            "updated_at": "2026-09-29T11:00:00Z",
        },
    }

    PUSH_PAYLOAD = {
        "object_kind": "push",
        "ref": "refs/heads/feat/my-feature",
        "user_username": "diana",
        "project": {"name": "payment-service"},
    }

    PIPELINE_PAYLOAD = {
        "object_kind": "pipeline",
        "project": {"name": "payment-service"},
        "object_attributes": {"status": "failed"},
    }

    def _post(self, event: str, payload: dict, token: str = "") -> "Response":
        headers = {
            "X-Gitlab-Event": event,
            "Content-Type": "application/json",
        }
        if token:
            headers["X-Gitlab-Token"] = token
        return client.post("/webhook/gitlab", json=payload, headers=headers)

    @patch("webhook_handler.call_risk_api", return_value=MOCK_ASSESSMENT)
    def test_mr_opened_is_assessed(self, mock_risk):
        resp = self._post("Merge Request Hook", self.MR_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "assessed"
        assert data["mr_iid"] == 7
        mock_risk.assert_called_once()

    @patch("webhook_handler.call_risk_api", return_value=MOCK_ASSESSMENT)
    def test_mr_merged_is_ignored(self, mock_risk):
        payload = dict(self.MR_PAYLOAD)
        payload["object_attributes"] = dict(payload["object_attributes"])
        payload["object_attributes"]["state"] = "merged"
        resp = self._post("Merge Request Hook", payload)
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"
        mock_risk.assert_not_called()

    def test_push_hook_is_recorded(self):
        resp = self._post("Push Hook", self.PUSH_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "recorded"
        assert data["branch"] == "feat/my-feature"
        assert data["pusher"] == "diana"

    def test_pipeline_hook_is_recorded(self):
        resp = self._post("Pipeline Hook", self.PIPELINE_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["status"] == "recorded"
        assert resp.json()["pipeline_status"] == "failed"

    def test_unknown_event_is_ignored(self):
        resp = self._post("Note Hook", {"object_kind": "note"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ignored"

    def test_invalid_token_returns_401(self):
        import webhook_handler
        original = webhook_handler.WEBHOOK_SECRET
        webhook_handler.WEBHOOK_SECRET = "mysecret"
        try:
            resp = self._post("Merge Request Hook", self.MR_PAYLOAD, token="wrong")
            assert resp.status_code == 401
        finally:
            webhook_handler.WEBHOOK_SECRET = original

    def test_valid_token_passes(self):
        import webhook_handler
        original = webhook_handler.WEBHOOK_SECRET
        webhook_handler.WEBHOOK_SECRET = "mysecret"
        try:
            with patch("webhook_handler.call_risk_api", return_value=MOCK_ASSESSMENT):
                resp = self._post("Merge Request Hook", self.MR_PAYLOAD, token="mysecret")
                assert resp.status_code == 200
        finally:
            webhook_handler.WEBHOOK_SECRET = original
