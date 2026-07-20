# CodeCrew — Project Memory

## What this is
Multi-agent DevOps orchestration platform. MS Teams is the sole user interface (chat-ops); the orchestrator routes requests to specialist agents that read JIRA, generate code, manage GitHub, and trigger CI/CD. Supervisor/orchestrator pattern built on LangGraph. This is a learning project (interview prep) with a couple of collaborators - optimize for clarity and consistency over cleverness.

## Source of truth for requirements
Requirements, acceptance criteria, and status live in **Jira project CDC** (obulirajs.atlassian.net), connected via GitHub for Atlassian. Always read the relevant ticket's AC before implementing a story. This file describes *how* we build, not *what* to build - don't duplicate ticket content here.

## Stack
Python, FastAPI, LangGraph, Anthropic Claude API (with a config-driven switch to local Ollama), MS Teams via Azure Bot Service (Bot Framework). pip + requirements.txt (not poetry/uv). Repo: github.com/obulirajs/codecrew (monorepo, backend/ is active; frontend/ reserved for future UI).

## Architecture (current)
```
adapters/       chat-platform in/out ONLY (Teams so far; Slack/Google Chat later - same NormalizedEvent contract)
clients/        external API wrappers (jira_client.py - JIRA REST v3, auth+retries+typed errors; jira_ticket_spec.py - pure data-shaping on top of it for the future codegen agent; github_client.py comes in Epic 3)
codegen/        Epic 2 codegen agent internals (workspace.py - git worktree lifecycle per ticket off one canonical clone; agent.py - headless invocation via the Claude Agent SDK, not a raw Messages API call - Epic 2's architecture decision, since codegen needs to explore the real repo before writing code)
orchestrator/   LangGraph state, nodes, graph wiring - one node per agent capability
llm_client.py   single entry point for all LLM calls (provider switch lives here only)
main.py         FastAPI routes
config.py       pydantic-settings, fails fast on missing secrets
```

## Conventions (non-negotiable - match these, don't reinvent)
- **Config**: all secrets/settings go through `app/config.py` (pydantic-settings). Never read `os.environ` elsewhere.
- **Logging**: structured JSON via `app/logging_config.py`. One logger per module: `codecrew.<module_name>`.
- **adapters/ vs clients/**: adapters are chat platforms only. clients are external system APIs (Jira, GitHub, CI). Don't mix these - it's what keeps the chat layer swappable.
- **clients/ vs codegen/**: `clients/` holds thin, reusable wrappers around an external system's REST API (auth, retries, typed errors) - Jira today, GitHub/CI later. The Claude Agent SDK code in `codegen/` is NOT that: `query()` spawns a whole subprocess-based coding agent with its own tool loop (file edits, bash, repo exploration), not a REST call being wrapped. Think of `codegen/`'s three files (workspace.py, agent.py, diff.py) as a capability module - a peer of `orchestrator/jira_agent.py`, not of `clients/jira_client.py` - that just isn't wired into the LangGraph graph as a node yet. This is also why `codegen/agent.py` is deliberately exempt from the `llm_client.py` rule below - it's a headless agent process, not a raw completion call.
- **LLM calls**: always go through `app/llm_client.py`'s `chat_completion()`. Never instantiate an Anthropic or Ollama client anywhere else. Provider chosen via `LLM_PROVIDER` env var (`anthropic` | `ollama`); cheap/strong model tiers resolved via `Settings.cheap_model` / `Settings.strong_model`.
- **Prompt caching**: `chat_completion()` applies Anthropic prompt caching (`cache_control`) to system prompts over 500 characters - shorter ones pass through as a plain string, uncached. Cache hit/write token counts (`cache_creation_input_tokens` / `cache_read_input_tokens`) are logged at debug level on every Anthropic call for verification.
- **LangGraph**: one node per agent/capability. Routing is via conditional edges keyed on `state["intent"]`, not if/else chains in a single node.
- **Blocking SDKs** (e.g. `botframework-connector`, which is sync): wrap in `asyncio.to_thread` so the FastAPI event loop isn't stalled.
- **Bot Framework activities**: filter on `payload["type"] == "message"` before processing - Teams/Web Chat send `typing` events too.
- **Pinned `starlette`/`uvicorn`**: `requirements.txt` pins both below what `claude-agent-sdk`'s own `mcp` dependency wants (it asks for `starlette>=0.48.0`/`uvicorn>=0.31.1`; we're on `starlette==0.38.6`/`uvicorn==0.30.6` for fastapi 0.115.0 compatibility). This works today but is a known latent conflict - see CDC-47. Don't casually bump either version without checking that ticket first.

## Status (update after each story - keep this section short, just epic/story + state)
- **Epic 0** (CDC-5): Done. Teams <-> FastAPI <-> LangGraph round trip verified against real Teams (not just Web Chat). GitHub for Atlassian connected (commits/PRs auto-link to tickets; Smart Commits enabled).
  - 0.7 Local rotating file logging (CDC-18): done
  - 0.8 Request correlation ID across all log lines (CDC-19): done
- **Epic 1** (CDC-11): In progress.
  - 1.1 Show ticket summary on request (CDC-12): done
  - 1.2 List tickets assigned to me (CDC-13): done
  - 1.3 JIRA client wrapper (CDC-14): done
  - 1.4 Extract structured acceptance criteria (CDC-15): done
  - 1.5 Unit tests with mocked JIRA API (CDC-16): done
- **Epic 2** (CDC-40): In progress.
  - 2.1 Generate code diff for a single ticket (CDC-41): done - `app/codegen/diff.py`'s `generate_diff()` feeds a CDC-15 `TicketSpec` to the headless agent, lets it edit real files in a worktree, then captures the actual `git diff` (not model free text) as `{diff_text, summary, files_changed}`. Stops short of commit/push/PR (Epic 3). Extended `ticket_workspace()` with `cleanup_on_success` so a successful run keeps its worktree alive for Epic 3 to commit from later; failure still always cleans up.
  - 2.3 Flag ambiguous requirements instead of guessing (CDC-43): done - `generate_diff()`'s prompt now tells the agent to leave files untouched and end its response with a delimited `<<<NEEDS_CLARIFICATION>>>...<<<END_NEEDS_CLARIFICATION>>>` block (parsed via regex, not substring matching) when acceptance criteria are vague, contradictory, or impossible as written. When present, `CodegenResult` comes back with `needs_clarification=True` and `clarifying_questions`, diff/files empty, and the worktree is cleaned up immediately (nothing for Epic 3 to commit). If the agent makes no changes and never raises the marker, that's now treated as an unexpected failure (`CodegenError`, logged), not a silent empty success.
  - 2.5 Lint/validate generated code before handoff to git agent (CDC-45): done - after CDC-41's diff capture, `generate_diff()` runs ruff (new dependency) against the `.py` files in `files_changed` (`--select=E9,F` - syntax errors + pyflakes only, not ruff's full style rule set; non-`.py` files skipped) and adds `lint_errors: list[str]` to `CodegenResult`. Non-empty `lint_errors` still returns a populated `diff_text`/`files_changed` and keeps the worktree (same as a clean run) - real code exists, just flawed - but signals Epic 3 must check `lint_errors` before committing. Clean runs are unchanged from CDC-41/CDC-43.
  - 2.2 Codegen works against a real repo checkout via git worktree (CDC-42): done
  - 2.7 Prefer CLAUDE_CODE_OAUTH_TOKEN over API key when available (CDC-50): done
  - 2.8 Scheduled cleanup of stale codegen worktrees past retention window (CDC-52): done - new `WORKTREE_RETENTION_HOURS` setting (default 48). `workspace.py` gained `list_ticket_worktrees()` (every per-ticket worktree off the canonical clone, excluding the clone's own "main" entry and any detached one) and `delete_ticket_branch()`. New standalone `scripts/sweep_stale_worktrees.py` - not a scheduler, run periodically via cron/Task Scheduler or by hand - ages each worktree by filesystem mtime (git tracks no creation time) and, once older than the retention window, removes it via the existing `remove_worktree()` (`--force`) then deletes its branch. No-op run logs a short summary line; verified end-to-end against a real repo, not just mocks.
  - Bug (CDC-51): fixed - re-running a ticket after its worktree was cleaned up falsely raised WorktreeInProgressError, because the duplicate check looked at branch existence, not actual worktree checkout state (`git worktree remove` leaves the branch behind). `create_worktree()` +