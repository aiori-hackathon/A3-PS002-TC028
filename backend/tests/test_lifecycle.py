from fastapi.testclient import TestClient
from app.main import app, init_db
import tempfile
from pathlib import Path

# Basic API lifecycle checks. Run from backend with:
#   pip install pytest httpx
#   pytest -q
def test_health():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["status"] == "ok"

def test_consent_grant_and_withdrawal():
    with TestClient(app) as client:
        site = "pytest-demo.local"
        grant = client.post("/api/consents", json={
            "site": site, "purpose": "analytics", "decision": "granted",
            "notice_version": "test-v1", "notice_text": "test notice"
        })
        assert grant.status_code == 200
        allowed = client.post("/api/protected/share", json={
            "site": site, "purpose": "analytics", "action": "test"
        })
        assert allowed.status_code == 200
        client.post("/api/consents", json={
            "site": site, "purpose": "analytics", "decision": "withdrawn",
            "notice_version": "test-v1", "notice_text": "test notice"
        })
        denied = client.post("/api/protected/share", json={
            "site": site, "purpose": "analytics", "action": "test"
        })
        assert denied.status_code == 403

def test_policy_change_detection():
    with TestClient(app) as client:
        site = "policy-test.local"
        url = "https://example.test/privacy"
        first = client.post("/api/policies/check", json={
            "site": site, "url": url, "policy_text": "policy one"
        }).json()
        second = client.post("/api/policies/check", json={
            "site": site, "url": url, "policy_text": "policy two"
        }).json()
        assert first["changed"] is False
        assert second["changed"] is True
