# CodeCrew backend

Epic 0 walking skeleton: a Teams message reaches the orchestrator, gets
classified, and an acknowledgment is sent back.

## Setup

```bash
# from inside backend/, with your existing venv activated
pip install -r requirements.txt
cp .env.example .env
# edit .env with your real ANTHROPIC_API_KEY, TEAMS_APP_ID, TEAMS_APP_PASSWORD,
# and TEAMS_TENANT_ID (Directory/tenant ID from the Entra app registration)
```

## Run locally

```bash
uvicorn app.main:app --reload --port 8000
```

Then check:
```bash
curl http://localhost:8000/health
```

## Run tests

```bash
pytest
```

## What's implemented (Epic 0)

| Story | File(s) | Status |
|---|---|---|
| 0.1 - Teams ack within 3s | `app/main.py`, `app/adapters/teams_adapter.py` | Done (real Bot Framework auth via botframework-connector) |
| 0.2 - Normalize into common event schema | `app/models/events.py`, `app/adapters/teams_adapter.py` | Done |
| 0.3 - Orchestrator + intent classification | `app/orchestrator/*.py` | Done |
| 0.4 - Fail-fast secrets/config | `app/config.py` | Done |
| 0.5 - Structured logging + health check | `app/logging_config.py`, `app/main.py` | Done |

## Folder structure

```
backend/
  app/
    adapters/        # platform-specific chat adapters (Teams now, Slack/Google Chat later)
    orchestrator/     # LangGraph state, nodes, and graph wiring
    models/           # shared pydantic schemas
    config.py         # env-based settings, fails fast on missing secrets
    logging_config.py # structured JSON logging
    main.py           # FastAPI app + routes
  tests/
  requirements.txt
  .env.example
```

## Next steps (Epic 1 - JIRA agent)

Add `app/agents/jira_agent.py` + a JIRA API client wrapper, then extend
`orchestrator/graph.py` with a conditional edge: when `intent == "jira_query"`,
route to a new `jira_agent` node instead of ending immediately.
