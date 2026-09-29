"""
seed.py — Populates the DB with rich demo data showing clear success/failure trends.
Run: python3 seed.py
"""
import asyncio
import database as db
import risk_scorer as rs

# (service, env, version, deployer, outcome, deploy_time)
DEPLOYMENTS = [
    # ── auth-service: starts bad, improves over time ──────────────────────────
    ("auth-service", "production", "v1.0.0", "alice", "success",     "2026-09-01T10:00:00Z"),
    ("auth-service", "production", "v1.0.1", "alice", "failed",      "2026-09-03T17:30:00Z"),  # after hours → fail
    ("auth-service", "production", "v1.0.2", "alice", "rolled_back", "2026-09-05T18:00:00Z"),  # rollback
    ("auth-service", "production", "v1.0.3", "bob",   "failed",      "2026-09-07T20:00:00Z"),  # night deploy → fail
    ("auth-service", "production", "v1.1.0", "alice", "success",     "2026-09-10T10:00:00Z"),  # team fixes it
    ("auth-service", "production", "v1.1.1", "alice", "success",     "2026-09-13T11:00:00Z"),
    ("auth-service", "production", "v1.1.2", "alice", "success",     "2026-09-16T09:30:00Z"),
    ("auth-service", "production", "v1.2.0", "alice", "success",     "2026-09-19T10:00:00Z"),
    ("auth-service", "production", "v1.2.1", "alice", "success",     "2026-09-22T10:00:00Z"),
    ("auth-service", "production", "v1.2.2", "alice", "success",     "2026-09-25T10:00:00Z"),
    ("auth-service", "staging",    "v1.2.3", "alice", "success",     "2026-09-28T11:00:00Z"),
    ("auth-service", "production", "v1.2.3", "alice", "success",     "2026-09-29T10:00:00Z"),

    # ── payment-service: consistently risky, high failure rate ────────────────
    ("payment-service", "production", "v2.0.0", "bob", "success",     "2026-09-01T09:00:00Z"),
    ("payment-service", "production", "v2.0.1", "bob", "success",     "2026-09-04T10:00:00Z"),
    ("payment-service", "production", "v2.0.2", "bob", "failed",      "2026-09-06T19:00:00Z"),  # late deploy
    ("payment-service", "production", "v2.0.3", "bob", "rolled_back", "2026-09-08T20:30:00Z"),  # night rollback
    ("payment-service", "production", "v2.0.4", "bob", "failed",      "2026-09-11T17:45:00Z"),
    ("payment-service", "production", "v2.0.5", "carol","success",    "2026-09-14T10:00:00Z"),  # carol takes over
    ("payment-service", "production", "v2.1.0", "bob", "failed",      "2026-09-17T18:30:00Z"),  # bob back → fails
    ("payment-service", "production", "v2.1.1", "carol","success",    "2026-09-20T09:00:00Z"),
    ("payment-service", "production", "v2.1.2", "bob", "rolled_back", "2026-09-23T21:00:00Z"),  # weekend night
    ("payment-service", "production", "v2.1.3", "carol","success",    "2026-09-26T10:00:00Z"),
    ("payment-service", "staging",    "v2.2.0", "carol","success",    "2026-09-28T14:00:00Z"),
    ("payment-service", "production", "v2.2.0", "carol","success",    "2026-09-29T11:00:00Z"),

    # ── api-gateway: very stable, almost always green ─────────────────────────
    ("api-gateway", "staging",    "v3.0.0", "carol", "success", "2026-09-02T10:00:00Z"),
    ("api-gateway", "production", "v3.0.0", "carol", "success", "2026-09-03T10:00:00Z"),
    ("api-gateway", "staging",    "v3.0.1", "carol", "success", "2026-09-07T11:00:00Z"),
    ("api-gateway", "production", "v3.0.1", "carol", "success", "2026-09-08T10:00:00Z"),
    ("api-gateway", "production", "v3.1.0", "carol", "failed",  "2026-09-13T22:00:00Z"),  # one bad night deploy
    ("api-gateway", "production", "v3.1.1", "carol", "success", "2026-09-15T10:00:00Z"),  # hotfix
    ("api-gateway", "staging",    "v3.1.2", "carol", "success", "2026-09-19T10:00:00Z"),
    ("api-gateway", "production", "v3.1.2", "carol", "success", "2026-09-20T10:00:00Z"),
    ("api-gateway", "staging",    "v3.2.0", "carol", "success", "2026-09-25T10:00:00Z"),
    ("api-gateway", "production", "v3.2.0", "carol", "success", "2026-09-27T10:00:00Z"),
    ("api-gateway", "production", "v3.2.1", "carol", "success", "2026-09-29T09:00:00Z"),

    # ── notification-svc: new service, rocky start ────────────────────────────
    ("notification-svc", "staging",    "v1.0.0", "alice", "success",     "2026-09-10T10:00:00Z"),
    ("notification-svc", "production", "v1.0.0", "alice", "failed",      "2026-09-12T17:00:00Z"),
    ("notification-svc", "production", "v1.0.1", "alice", "rolled_back", "2026-09-12T18:00:00Z"),
    ("notification-svc", "production", "v1.0.2", "alice", "success",     "2026-09-14T10:00:00Z"),
    ("notification-svc", "production", "v1.0.3", "alice", "failed",      "2026-09-18T19:30:00Z"),
    ("notification-svc", "production", "v1.1.0", "bob",   "success",     "2026-09-21T10:00:00Z"),
    ("notification-svc", "production", "v1.1.1", "alice", "success",     "2026-09-24T10:00:00Z"),
    ("notification-svc", "staging",    "v1.2.0", "alice", "success",     "2026-09-27T11:00:00Z"),
    ("notification-svc", "production", "v1.2.0", "alice", "success",     "2026-09-29T10:30:00Z"),

    # ── db-migration-svc: rare, always scary, mixed results ───────────────────
    ("db-migration-svc", "staging",    "v1.0.0", "bob",   "success",     "2026-09-05T10:00:00Z"),
    ("db-migration-svc", "production", "v1.0.0", "bob",   "failed",      "2026-09-06T14:00:00Z"),
    ("db-migration-svc", "production", "v1.0.1", "bob",   "rolled_back", "2026-09-06T15:30:00Z"),
    ("db-migration-svc", "production", "v1.0.2", "alice", "success",     "2026-09-09T10:00:00Z"),
    ("db-migration-svc", "staging",    "v1.1.0", "alice", "success",     "2026-09-20T10:00:00Z"),
    ("db-migration-svc", "production", "v1.1.0", "alice", "failed",      "2026-09-21T16:00:00Z"),
    ("db-migration-svc", "production", "v1.1.1", "alice", "success",     "2026-09-23T10:00:00Z"),
    ("db-migration-svc", "production", "v1.2.0", "alice", "success",     "2026-09-29T10:00:00Z"),
]

async def seed():
    import sqlite3
    conn = sqlite3.connect(db.DB_PATH)
    count = conn.execute("SELECT COUNT(*) FROM deployments").fetchone()[0]
    conn.close()
    if count > 0:
        print(f"DB already has {count} rows, skipping seed.")
        return
    for i, (svc, env, ver, deployer, outcome, deploy_time) in enumerate(DEPLOYMENTS):
        dep_id = f"dep-{i+1:03d}"
        db.insert_deployment(dep_id, svc, env, ver, deployer, deployed_at=deploy_time)
        db.record_outcome(dep_id, svc, outcome)
        await rs.retain_outcome(svc, env, outcome, ver, deployer)

    print(f"Seeded {len(DEPLOYMENTS)} deployments ✅")
    print("\nService failure rates:")
    for svc in ["auth-service", "payment-service", "api-gateway", "notification-svc", "db-migration-svc"]:
        rate = db.get_service_failure_rate(svc)
        total = len([d for d in DEPLOYMENTS if d[0] == svc])
        fails = len([d for d in DEPLOYMENTS if d[0] == svc and d[4] in ("failed","rolled_back")])
        print(f"  {svc:25s} {fails}/{total} failures → {rate*100:.0f}% failure rate")

asyncio.run(seed())
