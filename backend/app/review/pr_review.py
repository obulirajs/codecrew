"""
Produce a structured review of a GitHub PR's diff (story 4.2, CDC-31) -
the contract CDC-30 (4.1, posting the review to GitHub) consumes. Built
first despite the numbering, same reasoning CDC-42 was built before CDC-41.

Architecture decision (per the ticket): a plain strong-tier
chat_completion() call, not the Agent SDK - unlike codegen, reviewing a
diff doesn't need repo exploration; the PR's own diff already carries
per-file before/after context, which is enough for v1.

This story stops at producing the ReviewResult: it does not post anything
to GitHub (CDC-30's job) and does not decide auto-merge eligibility
(CDC-32's job).
"""

import json
import logging
import re
from typing import List, Literal

from pydantic import BaseModel, Field, ValidationError

from app.clients.github_client import GitHubClient
from app.config import get_settings
from app.llm_client import chat_completion

logger = logging.getLogger("codecrew.pr_review")

_SYSTEM_PROMPT = """You are an automated code review agent. You are given the changed files and diffs from a GitHub pull request. Review the change for correctness, security, and code quality risk.

Respond with ONLY a single valid JSON object - no prose, no markdown code fences, nothing before or after it - matching exactly this schema:

{
  "verdict": "approve" | "request_changes",
  "risk_score": <float between 0.0 and 1.0, where 0.0 is no risk and 1.0 is high risk>,
  "flagged_files": [<file paths with notable issues, empty list if none>],
  "file_comments": [{"file": <path>, "line": <line number in the new file>, "body": <comment text>}],
  "summary": <one paragraph review summary>
}

verdict must be exactly "approve" or "request_changes" - no other values.
flagged_files and file_comments may be empty lists if there are no issues.
Output nothing but the JSON object."""

_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL)


class ReviewParsingError(Exception):
    """
    Raised when the model's review output can't be parsed into a valid
    ReviewResult - malformed JSON, missing/invalid fields, or an
    out-of-schema verdict/risk_score. Must never be swallowed into a
    default result: a parsing failure has to surface as an error, never
    silently look like a safe/passing review.
    """


class FileComment(BaseModel):
    file: str
    line: int
    body: str


class ReviewResult(BaseModel):
    verdict: Literal["approve", "request_changes"]
    risk_score: float = Field(ge=0.0, le=1.0)
    flagged_files: List[str]
    file_comments: List[FileComment]
    summary: str


def _build_diff_text(files: List[dict]) -> str:
    parts = []
    for file in files:
        filename = file["filename"]
        patch = file.get("patch")
        if patch:
            parts.append(f"--- {filename} ---\n{patch}")
        else:
            parts.append(f"--- {filename} ---\n(no diff available - binary file or diff too large)")
    return "\n\n".join(parts)


def _parse_review_result(raw: str) -> ReviewResult:
    text = raw.strip()
    fence_match = _FENCE_RE.match(text)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ReviewParsingError(f"Review output was not valid JSON: {exc}. Raw output: {raw[:500]!r}") from exc

    if not isinstance(data, dict):
        raise ReviewParsingError(f"Review output JSON was not an object. Raw output: {raw[:500]!r}")

    try:
        return ReviewResult(**data)
    except ValidationError as exc:
        raise ReviewParsingError(f"Review output did not match the expected schema: {exc}") from exc


def review_pull_request(pr_number: int) -> ReviewResult:
    """
    Fetch `pr_number`'s changed files/patches and ask the strong-tier
    model for a structured review, parsed defensively into a
    ReviewResult. Raises ReviewParsingError - never a silent "approve" -
    if the model's output doesn't parse as valid JSON matching the
    schema.
    """
    settings = get_settings()

    with GitHubClient() as client:
        files = client.get_pull_request_files(pr_number)

    diff_text = _build_diff_text(files)
    user_message = f"Pull request #{pr_number} changed files:\n\n{diff_text}"

    raw = chat_completion(
        model=settings.strong_model,
        system=_SYSTEM_PROMPT,
        user_message=user_message,
        max_tokens=4096,
    )
    result = _parse_review_result(raw)

    logger.info(
        "Reviewed pull request",
        extra={
            "pr_number": pr_number,
            "verdict": result.verdict,
            "risk_score": result.risk_score,
            "flagged_files": result.flagged_files,
        },
    )
    return result
