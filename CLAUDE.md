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
orchestrator/   LangGraph state, nodes, graph wiring - one node per agent capability
llm_client.py   single entry point for all LLM calls (provider switch lives here only)
main.py         FastAPI routes
config.py       pydantic-settings, fails fast on missing secrets
```

## Conventions (non-negotiable - match these, don't reinvent)
- **Config**: all secrets/settings go through `app/config.py` (pydantic-settings). Never read `os.environ` elsewhere.
- **Logging**: structured JSON via `app/logging_config.py`. One logger per module: `codecrew.<module_name>`.
- **adapters/ vs clients/**: adapters are chat platforms only. clients are external system APIs (Jira, GitHub, CI). Don't mix these - it's what keeps the chat layer swappable.
- **LLM calls**: always go through `app/llm_client.py`'s `chat_completion()`. Never instantiate an Anthropic or Ollama client anywhere else. Provider chosen via `LLM_PROVIDER` env var (`anthropic` | `ollama`); cheap/strong model tiers resolved via `Settings.cheap_model` / `Settings.strong_model`.
- **LangGraph**: one node per agent/capability. Routing is via conditional edges keyed on `state["intent"]`, not if/else chains in a single node.
- **Blocking SDKs** (e.g. `botframework-connector`, which is sync): wrap in `asyncio.to_thread` so the FastAPI event loop isn't stalled.
- **Bot Framework activities**: filter on `payload["type"] == "message"` before processing - Teams/Web Chat send `typing` events too.

## Status (update after each story - keep this section short, just epic/story + state)
- **Epic 0** (CDC-5): Done. Teams <-> FastAPI <-> LangGraph round trip verified against real Teams (not just Web Chat). GitHub for Atlassian connected (commits/PRs auto-link to tickets; Smart Commits enabled).
  - 0.7 Local rotating file logging (CDC-18): done
  - 0.8 Request correlation ID across all log lines (CDC-19): done
- **Epic 1** (CDC-11): In progress.
  - 1.1 Show ticket summary on request (CDC-12): done
  - 1.2 List tickets assigned to me (CDC-13): done
  - 1.3 JIRA client wrapper (CDC-14): done
  - 1.4 Extract structured acceptance criteria (CDC-15): done
  - 1.5: not started

## Local dev
```bash
cd backend
# activate your existing venv
pip install -r requirements.txt
cp .env.example .env   # fill in your own keys - see Team notes
uvicorn app.main:app --reload --port 8000
```
Testing against real Teams: `ngrok http 8000` (update Azure Bot resource's Messaging endpoint to `<ngrok-url>/teams/messages` each time the tunnel restarts, unless using a reserved ngrok domain).

## Team notes (for collaborators)
- Each person needs their **own** `.env` (gitignored, never commit it): own `ANTHROPIC_API_KEY`, own `JIRA_API_TOKEN` (from id.atlassian.com/manage-profile/security/api-tokens), shared `JIRA_BASE_URL`/`JIRA_PROJECT_KEY=CDC`.
- Branch and commit naming: include the Jira ticket key (e.g. `CDC-18-jira-client`, commit `"CDC-18 implement retry logic"`) so GitHub for Atlassian auto-links work.
- When asking Claude Code to implement a story: point it at the Jira ticket key directly (Claude Code has read access to CDC) plus this file for conventions - don't re-paste requirements manually.
