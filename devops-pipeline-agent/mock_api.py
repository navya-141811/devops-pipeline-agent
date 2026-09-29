"""
mock_api.py — Fake risk-score API for Person 2 to develop against.
Swap the base URL to Person 1's real API when it is ready.

Run locally:
    uvicorn mock_api:app --reload --port 8000
"""

from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="DevOps Pipeline Agent — Mock API", version="0.1.0")


# ── Request / Response models ──────────────────────────────────────────────────

class RiskScoreRequest(BaseModel):
    service: str
    environment: str                # e.g. "production", "staging"
    diff: dict                      # {"files_changed": 3, "resources_modified": [...]}
    deployer: str
    deploy_time: str                # ISO-8601 timestamp


class RiskScoreResponse(BaseModel):
    service: str
    score: float                    # 0.0 (safe) → 1.0 (high risk)
    recommendation: str             # "proceed" | "review" | "hold"
    risk_factors: list[str]


class DeploymentRecord(BaseModel):
    deployment_id: str
    service: str
    environment: str
    version: str
    deployed_by: str
    outcome: str                    # "success" | "failed" | "rolled_back"


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    """Health check — used by docker-compose and CI."""
    return {"status": "ok", "mode": "mock"}


@app.post("/risk-score", response_model=RiskScoreResponse)
def get_risk_score(payload: RiskScoreRequest):
    """
    Returns a hardcoded mock risk score.
    Replace this URL with Person 1's real endpoint in Week 2.
    """
    # Simple mock logic so tests have something meaningful to assert on
    score = 0.35
    factors = ["mock data — real scorer not connected yet"]
    recommendation = "proceed"

    if payload.environment == "production":
        score += 0.2
        factors.append("Production environment adds baseline risk")

    if len(payload.diff.get("resources_modified", [])) > 0:
        score += 0.15
        factors.append("Infrastructure resources modified")

    score = min(round(score, 2), 1.0)
    recommendation = "hold" if score >= 0.7 else "review" if score >= 0.4 else "proceed"

    return RiskScoreResponse(
        service=payload.service,
        score=score,
        recommendation=recommendation,
        risk_factors=factors,
    )


@app.get("/deployments")
def list_deployments(service: Optional[str] = None, limit: int = 10):
    """Returns mock deployment history."""
    records = [
        {
            "deployment_id": "dep-001",
            "service": "auth-service",
            "environment": "production",
            "version": "v1.2.3",
            "deployed_by": "alice",
            "outcome": "success",
            "deployed_at": "2026-09-27T10:00:00Z",
        },
        {
            "deployment_id": "dep-002",
            "service": "payment-service",
            "environment": "production",
            "version": "v2.0.1",
            "deployed_by": "bob",
            "outcome": "rolled_back",
            "deployed_at": "2026-09-28T15:30:00Z",
        },
        {
            "deployment_id": "dep-003",
            "service": "auth-service",
            "environment": "staging",
            "version": "v1.2.4",
            "deployed_by": "alice",
            "outcome": "success",
            "deployed_at": "2026-09-29T08:00:00Z",
        },
    ]
    if service:
        records = [r for r in records if r["service"] == service]
    return records[:limit]


@app.post("/deployments/outcome")
def record_outcome(record: DeploymentRecord):
    """Records the outcome of a deployment (stub — logs to console in mock mode)."""
    print(f"[MOCK] Recorded outcome: {record.model_dump()}")
    return {"status": "recorded", "deployment_id": record.deployment_id}
