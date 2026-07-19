"""
Generate a code diff for a single ticket (story 2.1, CDC-41), built on top
of story 2.2's worktree lifecycle (workspace.py) and headless agent
invocation (agent.py).

Feeds CDC-15's structured TicketSpec (summary, acceptance_criteria,
ticket_type, labels) to the Agent SDK as the prompt - not the ticket's raw
text - and lets it explore and edit real files in a per-ticket worktree.
The actual diff is then captured via `git diff` against the worktree's
branch rather than asked of the model as free text, so the returned result
reflects real file changes, not just whatever the model claims it did.

This story stops at producing the diff: it never commits, pushes, or opens
a PR (that's Epic 3's job). On success the worktree is deliberately kept
(cleanup_on_success=False) so Epic 3 can commit directly from the same
worktree/branch later; on failure the worktree is still always cleaned up,
via workspace.py's unchanged default behavior.

Story 2.3 (CDC-43): the prompt also tells the agent not to guess when
acceptance criteria are vague, contradictory, or impossible as literally
written (e.g. a path outside the repo) - instead it must leave the
worktree untouched and end its response with a delimited
NEEDS_CLARIFICATION block. generate_diff() parses that block with a regex
(not fragile substring matching); when present, it returns
needs_clarification=True with clarifying_questions populated, diff_text/
files_changed empty, and cleans up the worktree immediately (nothing for
Epic 3 to commit). If the agent makes no file changes AND doesn't raise
that marker, that's an unexpected silent no-op, not a normal empty
success - it's logged and raised as a CodegenError.
"""

import logging
import re
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from pydantic import BaseModel, Field

from app.clients.jira_ticket_spec import TicketSpec
from app.codegen.agent import run_headless
from app.codegen.workspace import TicketWorkspace, remove_worktree, ticket_workspace

logger = logging.getLogger("codecrew.codegen_diff")

_CLARIFICATION_OPEN_TAG = "<<<NEEDS_CLARIFICATION>>>"
_CLARIFICATION_CLOSE_TAG = "<<<END_NEEDS_CLARIFICATION>>>"

_CLARIFICATION_BLOCK_RE = re.compile(
    re.escape(_CLARIFICATION_OPEN_TAG) + r"\s*(.*?)\s*" + re.escape(_CLARIFICATION_CLOSE_TAG),
    re.DOTALL,
)
_CLARIFICATION_QUESTION_RE = re.compile(r"^-\s+(.*\S)\s*$", re.MULTILINE)


class CodegenError(Exception):
    """
    Raised when the codegen run fails in a way that isn't a normal result:
    the actual git diff can't be captured after the agent runs, or the
    agent made no file changes without flagging why via a
    NEEDS_CLARIFICATION marker (CDC-43).
    """


class CodegenResult(BaseModel):
    diff_text: str
    summary: str
    files_changed: List[str]
    needs_clarification: bool = False
    clarifying_questions: List[str] = Field(default_factory=list)


def _build_prompt(ticket_key: str, spec: TicketSpec) -> str:
    criteria = "\n".join(f"- {c}" for c in spec.acceptance_criteria) or "(none provided)"
    labels = ", ".join(spec.labels) or "(none)"
    return (
        f"Implement ticket {ticket_key}: {spec.summary}\n\n"
        f"Ticket type: {spec.ticket_type}\n"
        f"Labels: {labels}\n\n"
        f"Acceptance criteria:\n{criteria}\n\n"
        "First, check whether the acceptance criteria above are actually "
        "implementable as literally written. If any part is vague, "
        "contradictory, or impossible - for example, it references a file "
        "path outside this repository, or two requirements can't both be "
        "satisfied - do not guess and do not silently substitute your own "
        "\"best effort\" interpretation. Instead:\n"
        "- Do not create, edit, or delete any files.\n"
        "- End your entire response with a block in exactly this format, "
        "with each specific clarifying question on its own line starting "
        "with \"- \":\n\n"
        f"{_CLARIFICATION_OPEN_TAG}\n"
        "- <your first clarifying question>\n"
        f"{_CLARIFICATION_CLOSE_TAG}\n\n"
        "Only include that block if you are NOT making any code changes.\n\n"
        "Otherwise, explore this repository first to understand its "
        "existing conventions, then write or edit the real files needed to "
        "satisfy the acceptance criteria above, using your file tools. "
        "Actually make the changes - do not just describe or print a diff "
        "instead of editing files.\n\n"
        "Do not run `git commit`, `git push`, or open a pull request; "
        "leave the changes uncommitted in the working tree.\n\n"
        "When you're done, reply with a short plain-text summary of what "
        "you changed and why."
    )


def _parse_clarification(agent_text: str) -> Optional[List[str]]:
    """
    Look for a NEEDS_CLARIFICATION block in the agent's response and pull
    out its "- " bulleted questions. Returns None if no block is present
    (the normal-path signal), or if the block is present but contains no
    parseable questions (malformed - treated the same as absent, since
    there's nothing usable to surface to the caller).
    """
    match = _CLARIFICATION_BLOCK_RE.search(agent_text)
    if not match:
        return None

    questions = _CLARIFICATION_QUESTION_RE.findall(match.group(1))
    return questions or None


def _strip_clarification_block(agent_text: str) -> str:
    stripped = _CLARIFICATION_BLOCK_RE.sub("", agent_text).strip()
    return stripped or agent_text


def _run_git(args: List[str], cwd: Path) -> subprocess.CompletedProcess:
    logger.debug("Running git command", extra={"args": args, "cwd": str(cwd)})
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def _capture_diff(workspace: TicketWorkspace) -> Tuple[str, List[str]]:
    """
    Stage everything - including new/untracked files - before diffing
    against HEAD, so the captured diff reflects the agent's complete set
    of real file changes, not just edits to files that already existed.
    Staging is not committing: it leaves the worktree exactly as CDC-41
    needs it to survive for Epic 3 to commit from later.
    """
    add_result = _run_git(["add", "-A"], cwd=workspace.path)
    if add_result.returncode != 0:
        raise CodegenError(f"git add failed for {workspace.ticket_key}: {add_result.stderr.strip()}")

    diff_result = _run_git(["diff", "--cached", "HEAD"], cwd=workspace.path)
    if diff_result.returncode != 0:
        raise CodegenError(f"git diff failed for {workspace.ticket_key}: {diff_result.stderr.strip()}")

    names_result = _run_git(["diff", "--cached", "--name-only", "HEAD"], cwd=workspace.path)
    if names_result.returncode != 0:
        raise CodegenError(f"git diff --name-only failed for {workspace.ticket_key}: {names_result.stderr.strip()}")
    files_changed = [line for line in names_result.stdout.splitlines() if line.strip()]

    return diff_result.stdout, files_changed


async def generate_diff(ticket_key: str, spec: TicketSpec) -> CodegenResult:
    """
    Run the codegen agent against `spec` inside a fresh worktree for
    `ticket_key`, and return the actual diff it produced.

    Three outcomes:
    - Normal success: the agent edited files: the worktree is left in
      place (not cleaned up) so a later Epic 3 step can commit directly
      from it.
    - Needs clarification (CDC-43): the agent flagged the acceptance
      criteria as unimplementable as written and made no changes. The
      worktree is cleaned up immediately - there's nothing for Epic 3 to
      commit - and the result carries needs_clarification=True plus the
      agent's clarifying_questions.
    - Failure: the agent run itself raises, the diff can't be captured, or
      the agent silently made no changes without flagging why (an
      unexpected no-op, raised as CodegenError). Either way the worktree
      is removed before the exception propagates, matching CDC-42's
      original always-cleanup behavior on the failure path.
    """
    prompt = _build_prompt(ticket_key, spec)

    with ticket_workspace(ticket_key, spec.summary, cleanup_on_success=False) as workspace:
        agent_text = await run_headless(workspace.path, prompt)

        clarifying_questions = _parse_clarification(agent_text)
        if clarifying_questions is not None:
            logger.info(
                "Codegen agent flagged ambiguous requirements, needs clarification",
                extra={"ticket_key": ticket_key, "clarifying_questions": clarifying_questions},
            )
            remove_worktree(workspace)
            return CodegenResult(
                diff_text="",
                summary=_strip_clarification_block(agent_text),
                files_changed=[],
                needs_clarification=True,
                clarifying_questions=clarifying_questions,
            )

        diff_text, files_changed = _capture_diff(workspace)

        if not files_changed:
            logger.error(
                "Codegen agent made no file changes and did not flag ambiguous "
                "requirements - unexpected silent no-op",
                extra={"ticket_key": ticket_key},
            )
            raise CodegenError(
                f"Agent run for {ticket_key} produced no file changes and no "
                "clarification request."
            )

    logger.info(
        "Generated diff for ticket",
        extra={"ticket_key": ticket_key, "files_changed": files_changed},
    )

    return CodegenResult(diff_text=diff_text, summary=agent_text, files_changed=files_changed)
