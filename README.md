# DevOps Pipeline Agent

An AI-powered deployment risk scoring agent that watches every deployment in your engineering organization and tells you — before it goes live — whether it is safe to deploy or not. It learns from every past deployment outcome, gets smarter over time, and surfaces the exact reasons why a deployment is risky so your team can act on it.

The agent integrates directly into GitHub and GitLab workflows. When a developer opens a pull request, the agent automatically scores the risk, posts a comment on the PR with a full risk report, and sends a Slack alert if the deployment needs closer attention. A live dashboard shows the full deployment history, risk trends over time, and per-service failure rates — all in one place.

---

## What It Does

When a developer opens or updates a pull request:

1. GitHub or GitLab sends a webhook event to the agent
2. The agent extracts the change details — files modified, environment, deployer, deploy time
3. The risk scoring engine computes a score from **0.0 (safe) → 1.0 (high risk)** using five weighted factors
4. A formatted risk report is posted as a comment directly on the PR or MR
5. If the score is ≥ 0.4, a Slack alert is sent to the team
6. When the deployment completes, the outcome (success / failed / rolled back) is recorded and fed back into memory so future scores improve

| Score | Recommendation | Meaning |
|-------|---------------|---------|
| 0.0 – 0.39 | ✅ PROCEED | Safe to merge and deploy |
| 0.4 – 0.69 | ⚠️ REVIEW | Review carefully before merging |
| 0.7 – 1.0 | 🚫 HOLD | Do not deploy without explicit approval |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend API | Python 3.12, FastAPI, Uvicorn |
| Risk Scoring Engine | Custom Python scoring engine |
| Memory Layer | Hindsight (vectorize-io) — persistent AI memory, falls back to in-process memory if not configured |
| Database | SQLite via Python's built-in `sqlite3` |
| HTTP Client | httpx |
| Data Validation | Pydantic v2 |
| Frontend Dashboard | HTML, CSS, JavaScript, Chart.js |
| CI/CD | GitLab CI/CD (lint → test → build → deploy) |
| Containerization | Docker, Docker Compose |
| Notifications | Slack Incoming Webhooks (Block Kit) |
| PR Comments | GitHub REST API, GitLab Notes API |
| Testing | pytest, pytest-asyncio |
| Linting | Ruff |
| Deployment | Render (free tier) |

---

## Workflow

### 1. Webhook Ingestion

A developer opens a pull request on GitHub or GitLab. The platform sends a webhook POST request to the agent's webhook handler running on port 8001.

The webhook handler (`webhook_handler.py`) receives the event, verifies the signature or secret token, extracts the relevant fields — service name, environment, diff size, deployer username, and timestamp — and forwards them to the risk scoring API.

### 2. Risk Scoring

The risk scoring engine (`risk_scorer.py`) computes a weighted score across five factors:

| Factor | Weight | What it measures |
|--------|--------|-----------------|
| Historical failure rate | 30% | How often this service has failed in the past, pulled from the SQLite database |
| Memory recall | 25% | Past incidents recalled from Hindsight memory for this specific service and environment |
| Environment | 20% | Production scores 1.0, staging 0.4, dev 0.1 |
| Diff size | 15% | Number of files changed, lines added/deleted, IaC resources modified |
| Deploy time | 10% | Weekends and after-hours deploys score higher risk |

The final score is a weighted sum capped at 1.0. The engine also produces a list of human-readable risk factors explaining exactly why the score is what it is.

### 3. Memory — How the Agent Learns

Every time a deployment outcome is recorded (success, failed, or rolled back), the agent stores a plain-English description of what happened into Hindsight memory, keyed by service name.

On the next risk score request for that service, the engine queries Hindsight for past incidents. If it recalls previous failures, the memory score increases — meaning the agent gets progressively more cautious about services that have a history of problems, even if the current diff looks small.

If Hindsight is not configured, the agent falls back to an in-process Python dictionary that provides the same behaviour within a single running session.

### 4. PR Comment

After scoring, `pr_bot.py` posts a formatted markdown comment directly on the pull request or merge request. The comment includes the risk score, a visual progress bar, the recommendation (PROCEED / REVIEW / HOLD), and the full list of risk factors. Old bot comments are deleted before posting so the PR stays clean on each update.

### 5. Slack Alert

If the score is ≥ 0.4, `slack_notifier.py` sends a Slack Block Kit message to the configured channel. The message includes the service name, environment, score, recommendation, risk factors, and a button linking directly to the PR.

### 6. Outcome Feedback Loop

When the deployment completes, GitHub or GitLab sends a deployment status webhook. The agent records the outcome in the SQLite database, updates the service's failure rate in `service_stats`, and retains the outcome in Hindsight memory. This closes the learning loop — the next risk score for that service will reflect what just happened.

### 7. Dashboard

The dashboard (`dashboard/index.html`) is a single-page app served directly by the FastAPI backend at the root URL. It polls the API every 30 seconds and displays:

- **Stat cards** — total deployments, success rate, average risk score, high-risk deploy count, rollback count
- **Risk trend chart** — a line chart of risk scores over time, with color-coded points (green / amber / red)
- **Deployment history table** — every deployment with service, environment, version, deployer, risk score bar, outcome badge, and timestamp. Filterable by service and outcome.

---

## Project Structure

```
devops-pipeline-agent/
├── api.py               # Real risk-score API — replaces mock, serves dashboard
├── database.py          # SQLite schema, deployment history, service failure rates
├── risk_scorer.py       # Risk scoring engine with Hindsight memory integration
├── webhook_handler.py   # Receives GitHub/GitLab webhooks, calls risk API
├── pr_bot.py            # Posts risk score comments on PRs/MRs
├── slack_notifier.py    # Sends Slack Block Kit alerts
├── seed.py              # Populates DB with demo data for the dashboard
├── mock_api.py          # Original mock API (kept for reference)
├── dashboard/
│   └── index.html       # Live dashboard — deployment history and risk trends
├── tests/
│   ├── test_webhook_handler.py
│   └── test_pr_bot.py
├── .gitlab-ci.yml       # CI/CD pipeline: lint → test → build → deploy
├── render.yaml          # Render deployment config
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Running Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Seed the database with demo data
python3 seed.py

# Start the API and dashboard (single command)
uvicorn api:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000** for the dashboard.
The API is available at **http://localhost:8000/docs** (auto-generated Swagger UI).

### Environment Variables

```
WEBHOOK_SECRET=your_webhook_secret
GITHUB_TOKEN=your_github_pat
GITLAB_TOKEN=your_gitlab_pat
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
HINDSIGHT_URL=http://localhost:8888        # optional — falls back to in-process memory
HINDSIGHT_API_KEY=your_key                 # optional
DB_PATH=deployments.db                    # optional — defaults to current directory
```

---

## CI/CD Pipeline

Every push to GitLab triggers the pipeline defined in `.gitlab-ci.yml`:

| Stage | What it does |
|-------|-------------|
| `lint` | Ruff syntax and style check across all Python files |
| `test` | pytest with JUnit XML report, runs on every branch and MR |
| `build` | Docker image build and push to GitLab Container Registry |
| `deploy:staging` | Auto-deploy to staging on the `dev` branch |
| `deploy:production` | Manual-gate deploy to production on the `main` branch |

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Dashboard (HTML) |
| GET | `/health` | Health check |
| POST | `/risk-score` | Score a deployment — returns score, recommendation, risk factors |
| POST | `/deployments/outcome` | Record deployment outcome — updates DB and memory |
| GET | `/deployments` | List deployment history (optional `?service=` and `?limit=` filters) |
| GET | `/deployments/stats/{service}` | Get failure rate for a specific service |
| POST | `/webhook/github` | GitHub webhook receiver |
| POST | `/webhook/gitlab` | GitLab webhook receiver |
