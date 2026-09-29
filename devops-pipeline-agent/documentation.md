Split by Layer
  
  Member 1 — Backend & Data
  ├── Event ingestion (webhooks from CI/CD)
  ├── Database schema + migrations
  ├── Risk scoring engine (Python)
  └── REST API to expose risk scores
  
  Member 2 — Integrations & Frontend
  ├── CI/CD pipeline hooks (GitHub Actions / Jenkins)
  ├── PR bot (comment risk scores on pull requests)
  ├── Simple dashboard (deployment history, risk trends)
  └── Alert correlation (PagerDuty / Slack notifications)


  Git Workflow (2 person)
  
  main
   └── dev
        ├── feat/backend-ingestion     ← Member 1
        ├── feat/risk-scorer           ← Member 1
        ├── feat/github-webhook        ← Member 2
        └── feat/pr-bot                ← Member 2
  
  - Never push directly to main
  - Each person reviews the other's PR before merge
  - Daily 10-min sync to unblock dependencies
  
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  Build Order (Who does what first)
  
  Since Member 2 depends on Member 1's API being ready:
  
  Week 1
    M1: DB schema + event ingestion API
    M2: Set up project repo, CI/CD pipeline, write webhook handlers (mock API responses)
  
  Week 2
    M1: Risk scorer logic + expose /risk-score endpoint
    M2: Connect webhooks to real API, build PR bot
  
  Week 3
    M1: Feedback loop (record deployment outcomes back to DB)
    M2: Dashboard + Slack alerts
  
  Week 4
    Both: Integration testing, bug fixes, demo prep
  
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  Shared Responsibilities
  
  ┌────────────────────────┬───────────────────────────────────────┐
  │ Task                   │ Who                                   │
  ├────────────────────────┼───────────────────────────────────────┤
  │ Architecture decisions │ Both (discuss together)               │
  ├────────────────────────┼───────────────────────────────────────┤
  │ Code reviews           │ Mandatory cross-review                │
  ├────────────────────────┼───────────────────────────────────────┤
  │ Deployments            │ Whoever isn't deploying reviews first │
  ├────────────────────────┼───────────────────────────────────────┤
  │ Documentation          │ Each documents their own layer        │
  └────────────────────────┴───────────────────────────────────────┘
  
  ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
  
  Tools to Coordinate
  
  - GitHub Projects — track tasks as cards
  - Slack / Discord — quick unblocking
  - Shared .env.example — so both have consistent local setup
  - Docker Compose — so both run the same local stack without "works on my machine"