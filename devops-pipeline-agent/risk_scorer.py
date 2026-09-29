"""
risk_scorer.py — Deployment risk scoring engine with memory.

Memory backend (auto-selected):
    - If HINDSIGHT_URL is set → uses Hindsight cloud/self-hosted
    - Otherwise              → uses in-process dict (free, no setup)

Scoring factors (weights sum to 1.0):
    0.30  service historical failure rate  (from DB)
    0.25  memory recall                    (past incidents for this service)
    0.20  environment                      (production > staging > dev)
    0.15  diff size                        (files changed, IaC resources)
    0.10  deploy time                      (weekends / after-hours)

Environment variables:
    HINDSIGHT_URL     — Hindsight base URL  (optional)
    HINDSIGHT_API_KEY — API key             (optional)
"""

import os
import re
from datetime import datetime, timezone

from database import get_service_failure_rate

HINDSIGHT_URL     = os.getenv("HINDSIGHT_URL", "")
HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY", "")

# In-process fallback memory: { service: [content_str, ...] }
_local_memory: dict[str, list[str]] = {}

# Lazy-init Hindsight client only if URL is configured
_client = None
if HINDSIGHT_URL:
    try:
        from hindsight_client import Hindsight
        _client = Hindsight(base_url=HINDSIGHT_URL, api_key=HINDSIGHT_API_KEY or None)
    except Exception as e:
        print(f"[HINDSIGHT] Client init failed, using local memory: {e}")

BANK_PREFIX = "devops-"


def _bank(service: str) -> str:
    return f"{BANK_PREFIX}{service}"


# ── Sub-scorers ────────────────────────────────────────────────────────────────

def _env_score(environment: str) -> float:
    return {"production": 1.0, "staging": 0.4, "dev": 0.1}.get(environment.lower(), 0.5)


def _diff_score(diff: dict) -> float:
    files     = int(diff.get("files_changed", 0))
    additions = int(diff.get("additions", 0))
    deletions = int(diff.get("deletions", 0))
    iac_count = len(diff.get("resources_modified", []))

    file_s = min(files / 20, 1.0)
    line_s = min((additions + deletions) / 500, 1.0)
    iac_s  = min(iac_count / 5, 1.0)

    return round((file_s * 0.4 + line_s * 0.3 + iac_s * 0.3), 3)


def _time_score(deploy_time: str) -> float:
    try:
        dt = datetime.fromisoformat(deploy_time.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone.utc)
        hour, weekday = dt.hour, dt.weekday()

        if weekday >= 5:         return 1.0   # weekend
        if hour < 6 or hour >= 20: return 0.8  # night
        if 16 <= hour < 20:      return 0.5   # late afternoon
        return 0.1                             # business hours
    except Exception:
        return 0.3


async def _memory_score(service: str, environment: str) -> tuple[float, list[str]]:
    """Returns (score, risk_factors) from memory (Hindsight or local fallback)."""
    factors: list[str] = []
    score = 0.0

    if _client:
        # ── Hindsight ──────────────────────────────────────────────────────────
        try:
            recall = await _client.arecall(
                bank_id=_bank(service),
                query=f"past deployment failures or incidents for {service} in {environment}",
            )
            if recall and len(recall) > 0:
                texts = [r.text for r in recall if hasattr(r, "text") and r.text]
                failures = sum(1 for t in texts if re.search(r"fail|rollback|incident|outage", t, re.I))
                score   = min(failures * 0.2, 1.0)
                factors = [f"Memory: {t[:120]}" for t in texts[:3]]
        except Exception as exc:
            print(f"[HINDSIGHT] Recall failed: {exc}")
    else:
        # ── Local in-process memory ────────────────────────────────────────────
        entries  = _local_memory.get(service, [])
        failures = sum(1 for t in entries if re.search(r"fail|rollback", t, re.I))
        if failures:
            score   = min(failures * 0.2, 1.0)
            factors = [f"Memory: {e[:120]}" for e in entries[-3:] if re.search(r"fail|rollback", e, re.I)]

    return score, factors


async def retain_outcome(service: str, environment: str, outcome: str,
                         version: str, deployed_by: str) -> None:
    """Store deployment outcome so future risk scores improve."""
    content = (
        f"Deployment of {service} v{version} to {environment} by {deployed_by} "
        f"resulted in: {outcome}. Timestamp: {datetime.utcnow().isoformat()}Z"
    )

    if _client:
        try:
            await _client.aretain(bank_id=_bank(service), content=content)
            print(f"[HINDSIGHT] Retained: {service} → {outcome}")
            return
        except Exception as exc:
            print(f"[HINDSIGHT] Retain failed, falling back to local: {exc}")

    _local_memory.setdefault(service, []).append(content)
    print(f"[MEMORY] Retained: {service} → {outcome}")


# ── Main scorer ────────────────────────────────────────────────────────────────

async def score(service: str, environment: str, diff: dict,
                deployer: str, deploy_time: str) -> dict:
    factors: list[str] = []

    failure_rate = get_service_failure_rate(service)
    if failure_rate > 0:
        factors.append(f"Service '{service}' has {failure_rate*100:.0f}% historical failure rate")

    mem_score, mem_factors = await _memory_score(service, environment)
    factors.extend(mem_factors)

    env_score = _env_score(environment)
    if environment.lower() == "production":
        factors.append("Production environment — elevated baseline risk")

    diff_score = _diff_score(diff)
    if diff_score > 0.5:
        factors.append(f"Large diff: {diff.get('files_changed', 0)} files changed")
    if diff.get("resources_modified"):
        factors.append(f"IaC resources modified: {', '.join(diff['resources_modified'][:3])}")

    time_score = _time_score(deploy_time)
    if time_score >= 0.8:
        factors.append("High-risk deploy window (weekend or after-hours)")
    elif time_score >= 0.5:
        factors.append("Late-afternoon deploy window")

    final = round(min(
        failure_rate * 0.30
        + mem_score  * 0.25
        + env_score  * 0.20
        + diff_score * 0.15
        + time_score * 0.10,
        1.0,
    ), 3)

    recommendation = "hold" if final >= 0.7 else "review" if final >= 0.4 else "proceed"

    if not factors:
        factors.append("No significant risk factors detected")

    return {"score": final, "recommendation": recommendation, "risk_factors": factors}
