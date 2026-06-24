import pytest

import pr_agent.tools.ticket_pr_compliance_check as ticket_check
from pr_agent.config_loader import get_settings


@pytest.fixture(autouse=True)
def _reset_related_tickets():
    settings = get_settings()
    original_required = settings.get("pr_reviewer.require_ticket_analysis_review", False)
    original_related = settings.get("related_tickets", [])
    settings.set("pr_reviewer.require_ticket_analysis_review", True)
    settings.set("related_tickets", [])
    try:
        yield
    finally:
        settings.set("pr_reviewer.require_ticket_analysis_review", original_required)
        settings.set("related_tickets", original_related)


@pytest.mark.asyncio
async def test_extract_and_cache_pr_tickets_normalizes_sub_issue_fields(monkeypatch):
    async def fake_extract_tickets(git_provider):
        return [{
            "ticket_id": 1,
            "ticket_url": "https://github.com/o/r/issues/1",
            "title": "Parent",
            "body": "Parent body",
            "sub_issues": [{
                "ticket_url": "https://github.com/o/r/issues/2",
                "title": "Child",
                "body": "Child body",
            }],
        }]

    monkeypatch.setattr(ticket_check, "extract_tickets", fake_extract_tickets)
    variables = {}

    await ticket_check.extract_and_cache_pr_tickets(object(), variables)

    assert variables["related_tickets"] == [
        {
            "ticket_url": "https://github.com/o/r/issues/2",
            "title": "Child",
            "body": "Child body",
            "labels": "",
            "requirements": "",
        },
        {
            "ticket_id": 1,
            "ticket_url": "https://github.com/o/r/issues/1",
            "title": "Parent",
            "body": "Parent body",
            "sub_issues": [{
                "ticket_url": "https://github.com/o/r/issues/2",
                "title": "Child",
                "body": "Child body",
                "labels": "",
                "requirements": "",
            }],
            "labels": "",
            "requirements": "",
        },
    ]
