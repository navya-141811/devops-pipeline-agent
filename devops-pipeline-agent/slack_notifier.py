"""
slack_notifier.py — Sends Slack alerts when a deployment risk is high.

Environment variables:
    SLACK_WEBHOOK_URL — Incoming webhook URL from your Slack app
    SLACK_CHANNEL     — Override channel (optional, webhook default is used if not set)

Usage:
    from slack_notifier import notify_high_risk, notify_deployment_outcome

Or run standalone for testing:
    python slack_notifier.py
"""

import os
import httpx
from datetime import datetime

SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
SLACK_CHANNEL     = os.getenv("SLACK_CHANNEL", "")


# ── Message builders ───────────────────────────────────────────────────────────

def _risk_color(score: float) -> str:
    """Slack attachment color based on risk level."""
    if score >= 0.7:
        return "#E74C3C"  # red
    if score >= 0.4:
        return "#F39C12"  # amber
    return "#2ECC71"      # green


def build_risk_alert(service: str, environment: str, assessment: dict, pr_url: str = "") -> dict:
    """
    Builds a Slack Block Kit message for a high-risk deployment.
    https://api.slack.com/block-kit
    """
    score          = assessment.get("score", 0.0)
    recommendation = assessment.get("recommendation", "proceed").upper()
    risk_factors   = assessment.get("risk_factors", [])
    emoji          = {"PROCEED": "✅", "REVIEW": "⚠️", "HOLD": "🚫"}.get(recommendation, "ℹ️")

    factors_text = "\n".join(f"• {f}" for f in risk_factors) or "• No risk factors identified"

    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji} High-Risk Deployment Detected",
                "emoji": True,
            },
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Service:*\n`{service}`"},
                {"type": "mrkdwn", "text": f"*Environment:*\n`{environment}`"},
                {"type": "mrkdwn", "text": f"*Risk Score:*\n`{score:.2f} / 1.00`"},
                {"type": "mrkdwn", "text": f"*Recommendation:*\n`{recommendation}`"},
            ],
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Risk Factors:*\n{factors_text}",
            },
        },
    ]

    if pr_url:
        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View PR / MR"},
                    "url": pr_url,
                    "style": "primary",
                }
            ],
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": f"🤖 devops-pipeline-agent · {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
            }
        ],
    })

    payload = {"blocks": blocks, "attachments": [{"color": _risk_color(score), "blocks": []}]}
    if SLACK_CHANNEL:
        payload["channel"] = SLACK_CHANNEL

    return payload


def build_outcome_notification(service: str, environment: str, outcome: str, version: str) -> dict:
    """Builds a simple deployment outcome message."""
    emoji = {"success": "✅", "failed": "❌", "rolled_back": "↩️"}.get(outcome, "ℹ️")
    color = {"success": "#2ECC71", "failed": "#E74C3C", "rolled_back": "#F39C12"}.get(outcome, "#95A5A6")

    payload = {
        "attachments": [
            {
                "color": color,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                f"{emoji} *Deployment {outcome.replace('_', ' ').title()}*\n"
                                f"Service: `{service}` · Env: `{environment}` · Version: `{version}`"
                            ),
                        },
                    }
                ],
            }
        ]
    }

    if SLACK_CHANNEL:
        payload["channel"] = SLACK_CHANNEL

    return payload


# ── Send helpers ───────────────────────────────────────────────────────────────

def _send(payload: dict) -> bool:
    """POSTs a message to the Slack Incoming Webhook URL."""
    if not SLACK_WEBHOOK_URL:
        print("[WARN] SLACK_WEBHOOK_URL not set — skipping Slack notification")
        return False

    try:
        response = httpx.post(SLACK_WEBHOOK_URL, json=payload, timeout=10.0)
        if response.text == "ok":
            print("[SLACK] Notification sent successfully")
            return True
        else:
            print(f"[ERROR] Slack returned: {response.status_code} — {response.text}")
            return False
    except httpx.RequestError as exc:
        print(f"[ERROR] Slack request failed: {exc}")
        return False


# ── Public API ─────────────────────────────────────────────────────────────────

def notify_high_risk(service: str, environment: str, assessment: dict, pr_url: str = "") -> bool:
    """
    Send a Slack alert if the risk score is high enough to warrant attention.
    Only fires if score >= 0.4 (review or hold).
    """
    score = assessment.get("score", 0.0)
    if score < 0.4:
        return False  # Proceed — no alert needed

    payload = build_risk_alert(service, environment, assessment, pr_url)
    return _send(payload)


def notify_deployment_outcome(service: str, environment: str, outcome: str, version: str = "unknown") -> bool:
    """Send a Slack message when a deployment completes (success, failed, or rolled_back)."""
    payload = build_outcome_notification(service, environment, outcome, version)
    return _send(payload)


# ── Local test ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Testing Slack notifier (will print [WARN] if SLACK_WEBHOOK_URL not set)...")

    notify_high_risk(
        service="auth-service",
        environment="production",
        assessment={
            "score": 0.75,
            "recommendation": "hold",
            "risk_factors": [
                "Service has 40% recent failure rate",
                "IAM role modification detected",
                "Deploy time is high-risk window (Friday 4pm)",
            ],
        },
        pr_url="https://gitlab.com/vaishnavisampeta90/devops-pipeline-agent/-/merge_requests/1",
    )

    notify_deployment_outcome(
        service="payment-service",
        environment="production",
        outcome="rolled_back",
        version="v2.0.1",
    )
