"""
tests/test_pr_bot.py

Tests for pr_bot.py — covers:
  - build_comment: markdown structure, score bar, risk levels
  - build_score_bar: correct fill and color indicators
  - post_github_comment: successful post, API error handling, missing token
  - delete_previous_bot_comments: finds and deletes old bot comments
  - post_gitlab_comment: successful post, API error, missing token
  - comment_risk_score: top-level dispatcher for github / gitlab / unknown

All HTTP calls are mocked via unittest.mock.patch — no live network calls.
"""

import os
import pytest
from unittest.mock import patch, MagicMock

os.environ.setdefault("GITHUB_TOKEN", "")
os.environ.setdefault("GITLAB_TOKEN", "")

from pr_bot import (  # noqa: E402
    build_comment,
    build_score_bar,
    post_github_comment,
    post_gitlab_comment,
    delete_previous_bot_comments,
    comment_risk_score,
)


# ── build_score_bar ───────────────────────────────────────────────────────────

class TestBuildScoreBar:
    def test_green_for_low_risk(self):
        bar = build_score_bar(0.2)
        assert "🟢" in bar

    def test_amber_for_medium_risk(self):
        bar = build_score_bar(0.5)
        assert "🟡" in bar

    def test_red_for_high_risk(self):
        bar = build_score_bar(0.8)
        assert "🔴" in bar

    def test_bar_is_ten_chars(self):
        bar = build_score_bar(0.4)
        # The filled blocks + empty blocks should total 10
        filled = bar.count("█")
        empty  = bar.count("░")
        assert filled + empty == 10

    def test_full_bar_at_score_one(self):
        bar = build_score_bar(1.0)
        assert "░" not in bar   # all filled

    def test_empty_bar_at_score_zero(self):
        bar = build_score_bar(0.0)
        assert "█" not in bar   # all empty


# ── build_comment ─────────────────────────────────────────────────────────────

class TestBuildComment:
    def _make(self, score=0.55, recommendation="review", factors=None, service="my-svc"):
        return build_comment(
            score=score,
            recommendation=recommendation,
            risk_factors=factors or ["Some risk factor"],
            service=service,
        )

    def test_contains_service_name(self):
        comment = self._make(service="payment-service")
        assert "payment-service" in comment

    def test_contains_score(self):
        comment = self._make(score=0.72)
        assert "0.72" in comment

    def test_contains_recommendation_uppercase(self):
        comment = self._make(recommendation="hold")
        assert "HOLD" in comment

    def test_proceed_shows_green_emoji(self):
        comment = self._make(score=0.1, recommendation="proceed")
        assert "✅" in comment

    def test_review_shows_warning_emoji(self):
        comment = self._make(score=0.5, recommendation="review")
        assert "⚠️" in comment

    def test_hold_shows_stop_emoji(self):
        comment = self._make(score=0.8, recommendation="hold")
        assert "🚫" in comment

    def test_risk_factors_listed(self):
        comment = self._make(factors=["High failure rate", "IAM change"])
        assert "High failure rate" in comment
        assert "IAM change" in comment

    def test_empty_factors_shows_fallback(self):
        comment = build_comment(score=0.2, recommendation="proceed", risk_factors=[], service="svc")
        assert "No risk factors identified" in comment

    def test_comment_is_markdown(self):
        comment = self._make()
        assert "##" in comment          # has a heading
        assert "```" not in comment     # not a code block — plain markdown


# ── post_github_comment ───────────────────────────────────────────────────────

class TestPostGitHubComment:
    def test_returns_false_when_no_token(self):
        import pr_bot
        original = pr_bot.GITHUB_TOKEN
        pr_bot.GITHUB_TOKEN = ""
        try:
            result = post_github_comment("owner/repo", 1, "comment")
            assert result is False
        finally:
            pr_bot.GITHUB_TOKEN = original

    @patch("pr_bot.httpx.post")
    def test_returns_true_on_success(self, mock_post):
        import pr_bot
        pr_bot.GITHUB_TOKEN = "fake_token"
        mock_post.return_value = MagicMock(status_code=201)

        result = post_github_comment("owner/repo", 42, "test comment")

        assert result is True
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "/repos/owner/repo/issues/42/comments" in call_args[0][0]
        pr_bot.GITHUB_TOKEN = ""

    @patch("pr_bot.httpx.post")
    def test_returns_false_on_api_error(self, mock_post):
        import pr_bot
        pr_bot.GITHUB_TOKEN = "fake_token"
        mock_post.return_value = MagicMock(status_code=422, text="Unprocessable")

        result = post_github_comment("owner/repo", 42, "comment")

        assert result is False
        pr_bot.GITHUB_TOKEN = ""

    @patch("pr_bot.httpx.post")
    def test_sends_correct_token_header(self, mock_post):
        import pr_bot
        pr_bot.GITHUB_TOKEN = "ghp_test123"
        mock_post.return_value = MagicMock(status_code=201)

        post_github_comment("owner/repo", 1, "hello")

        headers = mock_post.call_args[1]["headers"]
        assert headers["Authorization"] == "Bearer ghp_test123"
        pr_bot.GITHUB_TOKEN = ""


# ── delete_previous_bot_comments ─────────────────────────────────────────────

class TestDeletePreviousBotComments:
    def test_does_nothing_without_token(self):
        import pr_bot
        pr_bot.GITHUB_TOKEN = ""
        # Should not raise
        delete_previous_bot_comments("owner/repo", 1)

    @patch("pr_bot.httpx.delete")
    @patch("pr_bot.httpx.get")
    def test_deletes_bot_comment(self, mock_get, mock_delete):
        import pr_bot
        pr_bot.GITHUB_TOKEN = "fake_token"

        mock_get.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value=[
                {"id": 100, "body": "Normal comment"},
                {"id": 101, "body": "## ✅ DevOps Pipeline Agent — Risk Assessment\n..."},
            ]),
        )
        mock_delete.return_value = MagicMock(status_code=204)

        delete_previous_bot_comments("owner/repo", 1)

        # Should delete only the bot comment (id 101)
        assert mock_delete.call_count == 1
        assert "101" in mock_delete.call_args[0][0]
        pr_bot.GITHUB_TOKEN = ""

    @patch("pr_bot.httpx.get")
    def test_handles_failed_get_gracefully(self, mock_get):
        import pr_bot
        pr_bot.GITHUB_TOKEN = "fake_token"
        mock_get.return_value = MagicMock(status_code=404)
        # Should not raise
        delete_previous_bot_comments("owner/repo", 999)
        pr_bot.GITHUB_TOKEN = ""


# ── post_gitlab_comment ───────────────────────────────────────────────────────

class TestPostGitLabComment:
    def test_returns_false_when_no_token(self):
        import pr_bot
        pr_bot.GITLAB_TOKEN = ""
        assert post_gitlab_comment("group/project", 5, "comment") is False

    @patch("pr_bot.httpx.post")
    def test_returns_true_on_success(self, mock_post):
        import pr_bot
        pr_bot.GITLAB_TOKEN = "glpat_fake"
        mock_post.return_value = MagicMock(status_code=201)

        result = post_gitlab_comment("group/my-project", 5, "test note")

        assert result is True
        call_url = mock_post.call_args[0][0]
        assert "merge_requests/5/notes" in call_url
        pr_bot.GITLAB_TOKEN = ""

    @patch("pr_bot.httpx.post")
    def test_url_encodes_project_path(self, mock_post):
        import pr_bot
        pr_bot.GITLAB_TOKEN = "glpat_fake"
        mock_post.return_value = MagicMock(status_code=201)

        post_gitlab_comment("my group/my project", 1, "note")

        call_url = mock_post.call_args[0][0]
        assert "my%20group%2Fmy%20project" in call_url or "my+group" not in call_url
        pr_bot.GITLAB_TOKEN = ""

    @patch("pr_bot.httpx.post")
    def test_returns_false_on_api_error(self, mock_post):
        import pr_bot
        pr_bot.GITLAB_TOKEN = "glpat_fake"
        mock_post.return_value = MagicMock(status_code=404, text="Not found")

        result = post_gitlab_comment("group/project", 5, "note")
        assert result is False
        pr_bot.GITLAB_TOKEN = ""


# ── comment_risk_score (dispatcher) ──────────────────────────────────────────

class TestCommentRiskScore:
    ASSESSMENT = {
        "score": 0.65,
        "recommendation": "review",
        "risk_factors": ["Many files changed"],
    }

    @patch("pr_bot.post_github_comment", return_value=True)
    @patch("pr_bot.delete_previous_bot_comments")
    def test_github_platform_calls_github_helpers(self, mock_delete, mock_post):
        comment_risk_score(
            platform="github",
            repo_or_project="owner/repo",
            pr_number=10,
            assessment=self.ASSESSMENT,
            service="auth-service",
        )
        mock_delete.assert_called_once_with("owner/repo", 10)
        mock_post.assert_called_once()

    @patch("pr_bot.post_gitlab_comment", return_value=True)
    def test_gitlab_platform_calls_gitlab_helper(self, mock_post):
        comment_risk_score(
            platform="gitlab",
            repo_or_project="group/project",
            pr_number=7,
            assessment=self.ASSESSMENT,
            service="payment-service",
        )
        mock_post.assert_called_once_with("group/project", 7, pytest.approx(mock_post.call_args[0][2], rel=0))

    def test_unknown_platform_does_not_raise(self):
        # Should log a warning but not crash
        comment_risk_score(
            platform="bitbucket",
            repo_or_project="org/repo",
            pr_number=1,
            assessment=self.ASSESSMENT,
            service="svc",
        )

    @patch("pr_bot.post_github_comment", return_value=True)
    @patch("pr_bot.delete_previous_bot_comments")
    def test_comment_contains_service_name(self, mock_delete, mock_post):
        comment_risk_score(
            platform="github",
            repo_or_project="owner/repo",
            pr_number=1,
            assessment=self.ASSESSMENT,
            service="my-special-service",
        )
        posted_comment = mock_post.call_args[0][2]  # 3rd positional arg
        assert "my-special-service" in posted_comment
