# DevOps Pipeline Agent

An AI-powered deployment risk scoring agent that integrates into GitHub and GitLab CI/CD workflows. It automatically evaluates every pull request, assigns a risk score, posts a comment directly on the PR/MR, and sends Slack alerts when a change needs closer attention.

---

## What It Does

When a developer opens or updates a pull request:

1. GitHub/GitLab sends a webhook event to this service
2. The agent extracts the change details (files modified, environment, deployer, deploy time)
3. The risk scoring API computes a score from **0.0 (safe) → 1.0 (high risk)**
4. A formatted risk report is posted as a comment on the PR/MR
5. If the score is ≥ 0.4, a Slack alert is sent to the team

| Score | Recommendation | Action |
|-------|---------------|--------|
| 0.0 – 0.39 | ✅ PROCEED | Safe to merge |
| 0.4 – 0.69 | ⚠️ REVIEW | Review carefully before merging |
| 0.7 – 1.0 | 🚫 HOLD | Do not deploy without explicit approval |

---

## Project Structure

```
devops-pipeline-agent/
├── webhook_handler.py   # Receives GitHub/GitLab webhooks, calls risk API
├── mock_api.py          # Risk scoring API (FastAPI, mock implementation)
├── pr_bot.py            # Posts risk score comments on PRs/MRs
├── slack_notifier.py    # Sends Slack Block Kit alerts
├── dashboard/
│   └── index.html       # Browser dashboard — deployment history + risk trends
├── tests/
│   ├── test_webhook_handler.py
│   └── test_pr_bot.py
├── .gitlab-ci.yml       # CI/CD: lint → test → build → deploy
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

---

## Quick Start

### 1. Clone and set up environment

```bash
git clone https://gitlab.com/vaishnavisampeta90/devops-pipeline-agent.git
cd devops-pipeline-agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

```bash
cp .env.example .env
# Edit .env and fill in your values
```

Key variables:

```
WEBHOOK_SECRET=your_webhook_secret
GITHUB_TOKEN=your_github_pat
GITLAB_TOKEN=your_gitlab_pat
SLACK_WEBHOOK_URL=https://hooks.slack.com/...
RISK_API_URL=http://localhost:8000
```

### 3. Run with Docker Compose

```bash
docker-compose up
```

This starts:
- `mock_api` on port 8000 — risk scoring API
- `webhook_handler` on port 8001 — webhook receiver

### 4. Run locally (without Docker)

```bash
# Terminal 1 — start risk API
uvicorn mock_api:app --reload --port 8000

# Terminal 2 — start webhook handler
uvicorn webhook_handler:app --reload --port 8001
```

### 5. Open the dashboard

Open `dashboard/index.html` in your browser. It connects to `http://localhost:8000` by default.

---

## Running Tests

```bash
pytest tests/ -v
```

---

## Webhook Setup

### GitHub

In your GitHub repo → Settings → Webhooks → Add webhook:

- Payload URL: `http://your-server:8001/webhook/github`
- Content type: `application/json`
- Secret: value of `WEBHOOK_SECRET`
- Events: Pull requests, Pushes, Deployment statuses

### GitLab

In your GitLab project → Settings → Webhooks:

- URL: `http://your-server:8001/webhook/gitlab`
- Secret token: value of `WEBHOOK_SECRET`
- Trigger: Merge request events, Push events, Pipeline events

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12, FastAPI, Uvicorn |
| HTTP Client | httpx |
| Data Validation | Pydantic v2 |
| Frontend | HTML / CSS / JavaScript, Chart.js |
| CI/CD | GitLab CI/CD |
| Containerization | Docker, Docker Compose |
| Notifications | Slack Incoming Webhooks |
| Testing | pytest, pytest-asyncio |
| Linting | Ruff |

---

## CI/CD Pipeline

The `.gitlab-ci.yml` runs four stages on every push:

| Stage | What it does |
|-------|-------------|
| `lint` | Ruff syntax and style check |
| `test` | pytest with JUnit XML report |
| `build` | Docker image build and push to GitLab registry |
| `deploy:staging` | Auto-deploy to staging on `dev` branch |
| `deploy:production` | Manual-gate deploy to production on `main` branch |

---

## License

MIT
