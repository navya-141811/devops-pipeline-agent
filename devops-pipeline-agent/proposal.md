# DevOps Pipeline Agent — Project Proposal

---

## 1. Introduction

When developers push code or open a pull request, an automated CI/CD pipeline builds, tests, and deploys the code. Not every deployment is equally risky — a small documentation fix carries far less risk than a change that modifies infrastructure resources, touches authentication logic, or goes out on a Friday afternoon.

The problem is that teams treat every deployment the same way. There is no automatic signal telling developers or reviewers how risky a particular change is before it reaches production. Teams rely on manual judgment, which is inconsistent and slow.

Our project solves this by building an **AI-powered deployment risk scoring agent** that automatically evaluates every pull request and deployment, assigns a risk score, and alerts the team when a change needs closer attention.

---

## 2. Problem Statement

CI/CD pipelines handle deployments of all shapes and sizes:

- A small bug fix with 2 files changed
- A feature that modifies 30 files and adds new infrastructure
- A hotfix deployed at 11 PM on a Friday
- A change that modifies IAM roles or security policies

All of these get merged and deployed in the same way, with no automatic risk signal. This leads to:

- High-risk changes going to production without sufficient review
- Rollbacks that could have been avoided
- No consistent way to enforce review requirements based on change size or impact
- Teams discovering problems only after a deployment fails

---

## 3. Proposed Solution

We propose an **AI-powered deployment risk scoring agent** that integrates directly into the CI/CD workflow via webhooks.

When a pull request is opened or updated, the agent automatically:

1. Receives the event from GitHub or GitLab via a webhook
2. Analyzes the change (files modified, lines added/deleted, resources affected, environment, deploy time, deployer)
3. Calls a risk scoring API to compute a score from 0.0 (safe) to 1.0 (high risk)
4. Posts a formatted risk report as a comment directly on the PR/MR
5. Sends a Slack alert if the score is high enough to warrant team attention

The recommendation follows three tiers:

| Score | Recommendation | Meaning |
|-------|---------------|---------|
| 0.0 – 0.39 | ✅ PROCEED | Low risk, safe to merge |
| 0.4 – 0.69 | ⚠️ REVIEW | Needs careful review before merging |
| 0.7 – 1.0 | 🚫 HOLD | High risk, do not deploy without explicit approval |

---

## 4. How It Works

The system operates in two complementary flows:

### Flow A — Pre-Merge Risk Scoring

```
Code Push / PR Opened
       ↓
GitHub / GitLab Webhook
       ↓
Webhook Handler (webhook_handler.py)
       ↓
Risk Score API (mock_api.py → real scorer)
       ↓
Risk Assessment (score + recommendation + risk factors)
       ↓
PR/MR Comment (pr_bot.py)   +   Slack Alert (slack_notifier.py)
       ↓
Developer sees risk level before merging
       ↓
Dashboard (dashboard/index.html) — view deployment history + risk trends
```

### Flow B — Pipeline Failure Analysis & Memory

```
Developer pushes code
        ↓
CI/CD pipeline runs
        ↓
     Does it fail?
      ↙       ↘
    No         Yes
    ↓           ↓
  Deploy    Get error logs
                ↓
             AI Agent
                ↓
       Understand the error
                ↓
      Check previous failures
                ↓
       Similar one found?
          ↙          ↘
        Yes           No
         ↓             ↓
   Find old fix    Analyze as new
         ↓             ↓
         └──────┬──────┘
                ↓
        Explain the failure
                ↓
        Suggest a solution
                ↓
       Developer fixes it
                ↓
      Save the new experience
                ↓
        Use it next time
```

Flow A prevents risky changes from reaching production. Flow B handles failures that do occur — analyzing logs, searching past incidents, and building a growing knowledge base of solutions.

**Example output posted on a PR:**

```
## 🚫 DevOps Pipeline Agent — Risk Assessment

Service: auth-service
Risk Score: 0.75 🔴 ████████░░ 75%
Recommendation: HOLD

Risk Factors:
- Production environment adds baseline risk
- Infrastructure resources modified
- Deploy time is outside safe hours
```

---

## 5. Main Features

### Webhook Integration
Receives real-time events from GitHub and GitLab — pull requests, pushes, merge requests, pipeline events, and deployment status updates. Validates webhook signatures to ensure events are genuine.

### Risk Scoring API
Accepts deployment context (service name, environment, diff size, deployer, deploy time) and returns a risk score, recommendation, and list of contributing risk factors.

### PR / MR Bot
Automatically posts a formatted risk assessment comment on every pull request or merge request. Deletes the previous bot comment on re-push to keep PRs clean.

### Slack Notifications
Sends Block Kit alerts to a Slack channel when a deployment scores ≥ 0.4 (review or hold). Also notifies on deployment outcomes (success, failure, rollback).

### Deployment Dashboard
A browser-based dashboard that connects to the risk scoring API and displays:
- Total deployments, success rate, average risk score, high-risk count, rollback count
- Risk score trend chart over time
- Filterable deployment history table with risk bars, outcome badges, and timestamps

### GitLab CI/CD Pipeline
A full `.gitlab-ci.yml` with lint, test, Docker build, staging deploy, and production deploy (manual gate) stages.

### Pipeline Failure Analysis (Planned)
When a pipeline fails, the agent receives the error logs, uses an AI model to identify the root cause, and searches a vector database of previous failures for similar incidents. If a match is found, the previous fix is surfaced. If not, the failure is analyzed fresh. Either way, the explanation and suggested solution are posted back to the developer. The new incident and its resolution are saved for future reference.

---

## 6. Example

A developer opens a pull request that modifies IAM role configurations in the `auth-service` going to production on a Friday evening.

The agent receives the webhook, calls the risk scorer, and posts on the PR:

```
## 🚫 DevOps Pipeline Agent — Risk Assessment

Service: auth-service
Risk Score: 0.82 🔴 ████████░░ 82%
Recommendation: HOLD

Risk Factors:
- Production environment adds baseline risk
- Infrastructure resources modified (IAM roles)
- Deploy time is high-risk window (Friday evening)
```

Simultaneously, a Slack message fires in the `#deployments` channel alerting the team to review before merging.

### Example B — Pipeline Failure Analysis

A pipeline fails after a push with the following error:

```
npm ERR! ERESOLVE unable to resolve dependency tree
```

The agent receives the logs, identifies it as a dependency conflict, and searches previous failures:

```
Failure detected: Dependency installation failed

Similar failure found: Yes (matched from 2 weeks ago)

Previous cause:
  Incompatible version between react@18 and a plugin expecting react@17

Previous solution:
  Updated the conflicting package version and regenerated package-lock.json

Suggested action:
  Check the package versions involved and run npm install
  after resolving the dependency conflict.
```

The developer fixes it, and the solution is saved — so next time this happens, the answer is instant.

---

## 7. Technologies Used

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.12 |
| Web Framework | FastAPI + Uvicorn |
| HTTP Client | httpx |
| Data Validation | Pydantic v2 |
| Frontend | HTML / CSS / JavaScript (vanilla) |
| Charts | Chart.js |
| CI/CD | GitLab CI/CD |
| Containerization | Docker + Docker Compose |
| Notifications | Slack Incoming Webhooks (Block Kit) |
| Testing | pytest + pytest-asyncio |
| Linting | Ruff |
| Version Control | Git + GitLab |

---

## 8. Main Components

### 1. Webhook Handler (`webhook_handler.py`)
Receives GitHub and GitLab webhook events over HTTP. Validates request signatures, extracts relevant fields from the payload, and calls the risk scoring API. Handles: `pull_request`, `push`, `deployment_status` (GitHub) and `Merge Request Hook`, `Push Hook`, `Pipeline Hook` (GitLab).

### 2. Risk Scoring API (`mock_api.py`)
FastAPI service that accepts deployment context and returns a risk score, recommendation, and list of risk factors. Currently a mock implementation with rule-based logic — intended to be replaced with an ML or LLM-based scorer.

### 3. PR / MR Bot (`pr_bot.py`)
Posts formatted markdown risk assessment comments on GitHub Pull Requests and GitLab Merge Requests. Cleans up old bot comments on each update so PRs stay readable. Can also be run as a CLI tool.

### 4. Slack Notifier (`slack_notifier.py`)
Sends Slack Block Kit messages for high-risk deployments (score ≥ 0.4) and deployment outcome events (success, failure, rollback). Uses Slack Incoming Webhooks.

### 5. Dashboard (`dashboard/index.html`)
Single-page browser application that fetches data from the risk API and displays deployment history, stats, a risk score trend chart, and a filterable table. Auto-refreshes every 30 seconds.

### 6. GitLab CI/CD Pipeline (`.gitlab-ci.yml`)
Four-stage pipeline: lint → test → build Docker image → deploy. Staging deploys automatically on the `dev` branch; production requires a manual approval click in the GitLab UI.

---

## 9. Benefits

The system helps development teams:

- Get an automatic risk signal on every PR before it merges
- Enforce consistent review standards based on objective risk factors
- Reduce rollbacks by catching high-risk changes early
- Keep teams informed via Slack without manually monitoring pipelines
- View deployment history and risk trends through a central dashboard
- Spend less time reading large failure logs — the agent identifies the root cause
- Find previous solutions quickly instead of investigating from scratch
- Build a growing knowledge base of CI/CD problems and their fixes
- Avoid solving the same problem repeatedly across the team

---

## 10. Limitations

- The current risk scorer is rule-based (mock). The scoring logic needs to be extended with real ML or LLM-based analysis for more accurate results.
- Risk factors are based on metadata (file count, environment, deploy time). Deep code analysis (e.g., detecting security-sensitive changes) is not yet implemented.
- The system provides a recommendation but does not automatically block merges — it informs, not enforces. Enforcement would require additional integration with branch protection rules.

---

## 11. Future Improvements

- Replace the mock risk scorer with an LLM-based log and diff analyzer
- Add automatic blocking of PRs that score above a configurable threshold via GitHub/GitLab protected branch rules
- Store historical risk scores in a database and use them to improve future predictions
- Support multiple CI/CD platforms (Jenkins, GitHub Actions, CircleCI)
- Add a failure memory component — storing past deployment failures and their solutions for similarity search
- Track which deployments were actually rolled back and feed that signal back into the risk model
- Add analytics showing which services, deployers, or time windows historically produce the most high-risk deployments

---

## 12. Conclusion

This project provides an automated, AI-assisted way to assess deployment risk before code reaches production. By integrating directly into the pull request workflow via webhooks, it gives developers and reviewers an immediate, objective risk signal — without requiring them to manually evaluate every change. The combination of PR comments, Slack alerts, and a live dashboard makes deployment risk visible at every stage of the development process.
