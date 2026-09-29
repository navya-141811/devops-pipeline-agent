"""
webhook_handler.py — Receives GitHub/GitLab webhook events,
extracts the relevant info, and calls the risk-score API.

Run locally:
    uvicorn webhook_handler:app --reload --port 8001

Set your webhook secret in .env:
    WEBHOOK_SECRET=your_secret_here
    RISK_API_URL=http://localhost:8000
"""

import hashlib
import hmac
import os
import httpx

from fastapi import FastAPI, Request, HTTPException, Header
from typing import Optional

app = FastAPI(title="DevOps Pipeline Agent — Webhook Handler", version="0.1.0")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
RISK_API_URL   = os.getenv("RISK_API_URL", "http://localhost:8000")


# ── Signature verification ─────────────────────────────────────────────────────

def verify_github_signature(payload: bytes, signature: str) -> bool:
    """Validates the X-Hub-Signature-256 header from GitHub."""
    if not WEBHOOK_SECRET:
        return True  # Skip verification in dev if secret not set
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── Helpers ────────────────────────────────────────────────────────────────────

def call_risk_api(service: str, environment: str, diff: dict, deployer: str, deploy_time: str) -> dict:
    """Calls the risk-score API and returns the assessment."""
    try:
        response = httpx.post(
            f"{RISK_API_URL}/risk-score",
            json={
                "service": service,
                "environment": environment,
                "diff": diff,
                "deployer": deployer,
                "deploy_time": deploy_time,
            },
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as exc:
        print(f"[ERROR] Risk API unreachable: {exc}")
        return {"score": 0.0, "recommendation": "proceed", "risk_factors": ["Risk API unavailable"]}


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "webhook_handler"}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    """
    Receives GitHub webhook events.
    Handles: pull_request, push, deployment_status
    """
    body = await request.body()

    # Verify signature
    if x_hub_signature_256 and not verify_github_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = await request.json()
    event   = x_github_event or "unknown"

    print(f"[WEBHOOK] Received GitHub event: {event}")

    if event == "pull_request":
        return handle_pull_request(payload)

    if event == "push":
        return handle_push(payload)

    if event == "deployment_status":
        return handle_deployment_status(payload)

    return {"status": "ignored", "event": event}


@app.post("/webhook/gitlab")
async def gitlab_webhook(
    request: Request,
    x_gitlab_token: Optional[str] = Header(None),
    x_gitlab_event: Optional[str] = Header(None),
):
    """
    Receives GitLab webhook events.
    Handles: Merge Request Hook, Push Hook, Pipeline Hook
    """
    # Validate secret token
    if WEBHOOK_SECRET and x_gitlab_token != WEBHOOK_SECRET:
        raise HTTPException(status_code=401, detail="Invalid token")

    payload = await request.json()
    event   = x_gitlab_event or "unknown"

    print(f"[WEBHOOK] Received GitLab event: {event}")

    if event == "Merge Request Hook":
        return handle_gitlab_merge_request(payload)

    if event == "Push Hook":
        return handle_gitlab_push(payload)

    if event == "Pipeline Hook":
        return handle_gitlab_pipeline(payload)

    return {"status": "ignored", "event": event}


# ── Event handlers ─────────────────────────────────────────────────────────────

def handle_pull_request(payload: dict) -> dict:
    """Scores risk for a newly opened/updated PR."""
    action = payload.get("action")
    if action not in ("opened", "synchronize"):
        return {"status": "ignored", "action": action}

    pr      = payload.get("pull_request", {})
    repo    = payload.get("repository", {})
    service = repo.get("name", "unknown")
    deployer = pr.get("user", {}).get("login", "unknown")

    diff = {
        "files_changed": pr.get("changed_files", 0),
        "additions":     pr.get("additions", 0),
        "deletions":     pr.get("deletions", 0),
        "resources_modified": [],  # Populated by IaC diff parser in full implementation
    }

    assessment = call_risk_api(
        service=service,
        environment="production",
        diff=diff,
        deployer=deployer,
        deploy_time=pr.get("updated_at", ""),
    )

    print(f"[RISK] PR #{pr.get('number')} — score={assessment.get('score')} "
          f"recommendation={assessment.get('recommendation')}")

    return {
        "status": "assessed",
        "pr_number": pr.get("number"),
        "risk_assessment": assessment,
    }


def handle_push(payload: dict) -> dict:
    """Records a push event."""
    ref    = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "")
    pusher = payload.get("pusher", {}).get("name", "unknown")
    repo   = payload.get("repository", {}).get("name", "unknown")
    print(f"[PUSH] {pusher} pushed to {repo}/{branch}")
    return {"status": "recorded", "branch": branch, "pusher": pusher}


def handle_deployment_status(payload: dict) -> dict:
    """Records deployment outcome back to the API."""
    deployment = payload.get("deployment", {})
    status     = payload.get("deployment_status", {})
    service    = payload.get("repository", {}).get("name", "unknown")
    outcome    = status.get("state", "unknown")  # success | failure | error

    outcome_map = {"success": "success", "failure": "failed", "error": "failed"}

    try:
        httpx.post(
            f"{RISK_API_URL}/deployments/outcome",
            json={
                "deployment_id": str(deployment.get("id", "")),
                "service": service,
                "environment": deployment.get("environment", "unknown"),
                "version": deployment.get("sha", "unknown")[:8],
                "deployed_by": deployment.get("creator", {}).get("login", "unknown"),
                "outcome": outcome_map.get(outcome, "unknown"),
            },
            timeout=10.0,
        )
    except httpx.RequestError as exc:
        print(f"[ERROR] Could not record outcome: {exc}")

    return {"status": "recorded", "outcome": outcome}


def handle_gitlab_merge_request(payload: dict) -> dict:
    """GitLab MR opened — score its risk."""
    attrs    = payload.get("object_attributes", {})
    state    = attrs.get("state")
    if state not in ("opened", "updated"):
        return {"status": "ignored", "state": state}

    service  = payload.get("project", {}).get("name", "unknown")
    deployer = payload.get("user", {}).get("username", "unknown")

    diff = {
        "files_changed": attrs.get("changes_count", 0),
        "resources_modified": [],
    }

    assessment = call_risk_api(
        service=service,
        environment="production",
        diff=diff,
        deployer=deployer,
        deploy_time=attrs.get("updated_at", ""),
    )

    print(f"[RISK] MR !{attrs.get('iid')} — score={assessment.get('score')} "
          f"recommendation={assessment.get('recommendation')}")

    return {"status": "assessed", "mr_iid": attrs.get("iid"), "risk_assessment": assessment}


def handle_gitlab_push(payload: dict) -> dict:
    branch = payload.get("ref", "").replace("refs/heads/", "")
    pusher = payload.get("user_username", "unknown")
    repo   = payload.get("project", {}).get("name", "unknown")
    print(f"[PUSH] {pusher} pushed to {repo}/{branch}")
    return {"status": "recorded", "branch": branch, "pusher": pusher}


def handle_gitlab_pipeline(payload: dict) -> dict:
    attrs   = payload.get("object_attributes", {})
    status  = attrs.get("status")
    service = payload.get("project", {}).get("name", "unknown")
    print(f"[PIPELINE] {service} pipeline status: {status}")
    return {"status": "recorded", "pipeline_status": status}
