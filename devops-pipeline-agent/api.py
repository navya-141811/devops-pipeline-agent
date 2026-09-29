"""
api.py — Real risk-score API (replaces mock_api.py).

Run locally:
    uvicorn api:app --reload --port 8000

Environment variables:
    DB_PATH           — SQLite file path     (default: deployments.db)
    HINDSIGHT_URL     — Hindsight base URL   (default: http://localhost:8888)
    HINDSIGHT_API_KEY — Hindsight API key    (optional)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional

import database as db
import risk_scorer as scorer

from contextlib import asynccontextmanager

async def _startup():
    import subprocess, sys
    subprocess.run([sys.executable, "seed.py"], check=False)

@asynccontextmanager
async def lifespan(app):
    await _startup()
    yield

app = FastAPI(title="DevOps Pipeline Agent — Risk API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="dashboard"), name="static")

@app.get("/")
def dashboard():
    return FileResponse("dashboard/index.html")


# ── Models ─────────────────────────────────────────────────────────────────────

class RiskScoreRequest(BaseModel):
    service: str
    environment: str
    diff: dict
    deployer: str
    deploy_time: str


class RiskScoreResponse(BaseModel):
    service: str
    score: float
    recommendation: str
    risk_factors: list[str]


class DeploymentRecord(BaseModel):
    deployment_id: str
    service: str
    environment: str
    version: str
    deployed_by: str
    outcome: str          # "success" | "failed" | "rolled_back"


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "mode": "live"}


@app.post("/risk-score", response_model=RiskScoreResponse)
async def get_risk_score(payload: RiskScoreRequest):
    """Score deployment risk using DB history + Hindsight memory."""
    result = await scorer.score(
        service=payload.service,
        environment=payload.environment,
        diff=payload.diff,
        deployer=payload.deployer,
        deploy_time=payload.deploy_time,
    )

    return RiskScoreResponse(service=payload.service, **result)


@app.post("/deployments/outcome")
async def record_outcome(record: DeploymentRecord):
    """
    Record deployment outcome — updates DB stats and teaches Hindsight memory.
    Called by webhook_handler after a deployment_status event.
    """
    db.record_outcome(record.deployment_id, record.service, record.outcome)

    # Teach Hindsight so future risk scores improve
    await scorer.retain_outcome(
        service=record.service,
        environment=record.environment,
        outcome=record.outcome,
        version=record.version,
        deployed_by=record.deployed_by,
    )

    return {"status": "recorded", "deployment_id": record.deployment_id}


@app.get("/deployments")
def list_deployments(service: Optional[str] = None, limit: int = 10):
    """Return deployment history from DB."""
    return db.list_deployments(service=service, limit=limit)


@app.get("/deployments/stats/{service}")
def service_stats(service: str):
    """Return failure rate for a service."""
    rate = db.get_service_failure_rate(service)
    return {"service": service, "failure_rate": rate}
