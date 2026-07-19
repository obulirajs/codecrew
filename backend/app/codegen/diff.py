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
"""

import logging
import subprocess
from pathlib import Path
from typing import List, Tuple

from pydantic import BaseModel

from app.clients.jira_ticket_spec import TicketSpec
from app.codegen.agent import run_headless
from app.codegen.workspace import TicketWorkspace, ticket_workspace

logger = logging.getLogger("codecrew.codegen_diff")


class CodegenError(Exception):
    """Raised when the actual git diff can't be captured after the agent runs."""


class CodegenResult(BaseModel):
    diff_text: str
    summary: str
    files_changed: List[str]


def _build_prompt(ticket_key: str, spec: TicketSpec) -> str:
    criteria = "\n".join(f"- {c}" for c in spec.acceptance_criteria) or "(none provided)"
    labels = ", ".join(spec.labels) or "(none)"
    return (
        f"Implement ticket {ticket_key}: {spec.summary}\n\n"
        f"Ticket type: {spec.ticket_type}\n"
        f"Labels: {labels}\n\n"
        f"Acceptance criteria:\n{criteria}\n\n"
        "Explore this repository first to understand its existing "
        "conventions, then write or edit the real files needed to satisfy "
        "the acceptance criteria above, using your file tools. Actually "
        "make the changes - do not just describe or print a diff instead "
        "of editing files.\n\n"
        "Do not run `git commit`, `git push`, or open a pull request; "
        "leave the changes uncommitted in the working tree.\n\n"
        "When you're done, reply with a short plain-text summary of what "
        "you changed and why."
    )


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

    On success, the worktree is left in place (not cleaned up) so a later
    Epic 3 step can commit directly from it. On any failure - the agent
    run, or the diff capture itself - the worktree is removed before the
    exception propagates, matching CDC-42's original always-cleanup
    behavior on the failure path.
    """
    prompt = _build_prompt(ticket_key, spec)

    with ticket_workspace(ticket_key, spec.summary, cleanup_on_success=False) as workspace:
        agent_summary = await run_headless(workspace.path, prompt)
        diff_text, files_changed = _capture_diff(workspace)

    logger.info(
        "Generated diff for ticket",
        extra={"ticket_key": ticket_key, "files_changed": files_changed},
    )

    return CodegenResult(diff_text=diff_text, summary=agent_summary, files_changed=files_changed)
