"""
Unit tests for app/clients/jira_ticket_spec.py (story 1.5, CDC-16).

Pure function - no JiraClient, no HTTP, no network calls involved at all.
"""

from app.clients.jira_ticket_spec import extract_ticket_spec


def _issue(description, ticket_type="Story", labels=None):
    return {
        "fields": {
            "summary": "Some ticket",
            "issuetype": {"name": ticket_type},
            "labels": labels or [],
            "description": description,
        }
    }


def _paragraph(text, bold=False):
    node = {"type": "text", "text": text}
    if bold:
        node["marks"] = [{"type": "strong"}]
    return {"type": "paragraph", "content": [node]}


def _bullet_list(items):
    return {
        "type": "bulletList",
        "content": [
            {"type": "listItem", "content": [{"type": "paragraph", "content": [{"type": "text", "text": item}]}]}
            for item in items
        ],
    }


def test_ac_section_with_bullets_parses_into_separate_items():
    description = {
        "type": "doc",
        "content": [
            _paragraph("Intro sentence."),
            _paragraph("Acceptance criteria", bold=True),
            _bullet_list(["First criterion", "Second criterion"]),
        ],
    }
    spec = extract_ticket_spec(_issue(description, ticket_type="Story", labels=["backend"]))

    assert spec.summary == "Some ticket"
    assert spec.ticket_type == "Story"
    assert spec.labels == ["backend"]
    assert spec.acceptance_criteria == ["First criterion", "Second criterion"]


def test_description_with_no_ac_section_returns_empty_list():
    description = {
        "type": "doc",
        "content": [_paragraph("Just a goal statement, no AC section here.")],
    }
    spec = extract_ticket_spec(_issue(description))

    assert spec.acceptance_criteria == []


def test_no_description_returns_empty_list():
    spec = extract_ticket_spec(_issue(description=None))

    assert spec.acceptance_criteria == []


def test_ac_section_stops_at_next_bold_header():
    description = {
        "type": "doc",
        "content": [
            _paragraph("Acceptance criteria", bold=True),
            _bullet_list(["Only criterion"]),
            _paragraph("Definition of done", bold=True),
            _paragraph("This should not be treated as a criterion."),
        ],
    }
    spec = extract_ticket_spec(_issue(description))

    assert spec.acceptance_criteria == ["Only criterion"]


def test_inline_given_when_then_sentence_is_one_criterion():
    description = {
        "type": "doc",
        "content": [
            {
                "type": "paragraph",
                "content": [
                    {"type": "text", "text": "Acceptance criteria: ", "marks": [{"type": "strong"}]},
                    {"type": "text", "text": "Given X, when Y, then Z."},
                ],
            }
        ],
    }
    spec = extract_ticket_spec(_issue(description))

    assert spec.acceptance_criteria == ["Given X, when Y, then Z."]
