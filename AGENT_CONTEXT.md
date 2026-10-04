# AGENT_CONTEXT

Machine-oriented state file for coding agents. Read fully before any change.
UPDATE THIS FILE IN THE SAME COMMIT AS ANY CHANGE IT DESCRIBES. See `## update_protocol`.

```yaml
meta:
  project: eevee_assistant
  root: /Users/tako/root/eevee_assistant
  last_updated: 2026-10-04
  git_branch_main: main
```

## layout

```
apps/
  backend/            FastAPI service. ONLY app currently implemented.
    main.py           App entrypoint. Mounts routers. Defines GET /.
    auth.py           API-key header dependency. Shared by all routes.
    routes/
      __init__.py     Empty. Marks package.
      voice.py        router for /voice/*
    requirements.txt
    .env.example      Template. Real .env is gitignored.
  ui/                 EMPTY. Reserved for frontend. Not yet started.
infra/
  docker/
    docker-compose.yml       Single service: backend.
    .env.example             Template for compose env_file.
    backend/Dockerfile       Build for apps/backend.
.gitignore
AGENT_CONTEXT.md      This file.
```

## stack

```yaml
backend:
  language: python
  python_version: "3.13"      # pinned in Dockerfile base image
  framework: fastapi
  server: uvicorn
  deps_file: apps/backend/requirements.txt
  deps: [fastapi, "uvicorn[standard]", python-dotenv]
  listen: 0.0.0.0:8000        # hardcoded in Dockerfile CMD and main.py __main__
ui:
  status: not_started
```

## auth

```yaml
mechanism: static_shared_secret
header: X-API-Key             # auth.API_KEY_HEADER; matching is case-insensitive per HTTP spec
env_var: API_KEY              # read via os.environ.get at request time
dependency: auth.require_api_key
responses:
  missing_or_wrong_header: 401
  API_KEY_unset_on_server: 500
```

RULE: every new route MUST be guarded. Pattern:

```python
from fastapi import APIRouter, Depends
from auth import require_api_key

router = APIRouter()

@router.get("/thing", dependencies=[Depends(require_api_key)])
def thing():
    return {"status": "ok"}
```

Guard may be applied per-endpoint (current style) or once on the router
(`APIRouter(dependencies=[Depends(require_api_key)])`). Prefer router-level for
new routes with >2 endpoints. Do not leave an endpoint unguarded without
recording an explicit exception under `## decisions`.

## routes

| method | path           | module                | auth | returns                                              |
|--------|----------------|-----------------------|------|------------------------------------------------------|
| GET    | `/`            | `main.py`             | yes  | `{"status":"ok","service":"eevee-assistant-backend"}` |
| GET    | `/voice/health`| `routes/voice.py`     | yes  | `{"status":"ok","route":"voice"}`                     |

## conventions

```yaml
imports:
  style: flat            # routes import `from auth import ...`, NOT `from ..auth`
  reason: WORKDIR is /app and apps/backend/ contents are copied to /app root.
           Backend runs with apps/backend/ as cwd. No parent package exists.
           Relative/`backend.`-prefixed imports WILL break the container.
new_route_checklist:
  - create apps/backend/routes/<name>.py with `router = APIRouter()`
  - guard endpoints with Depends(require_api_key)
  - in main.py: `from routes import <name>` and
    `app.include_router(<name>.router, prefix="/<name>", tags=["<name>"])`
  - add row to `## routes` table above
  - add any new env var to `## env` below AND to BOTH .env.example files
env_files:
  - apps/backend/.env.example   # local dev template
  - infra/docker/.env.example   # container template
  - both must list the same keys. Real .env files are gitignored; never commit one.
secrets:
  - never hardcode a key in source, compose, or this file
  - never write a real value into .env.example
```

## env

| var       | required | consumed_by  | notes                                  |
|-----------|----------|--------------|----------------------------------------|
| `API_KEY` | yes      | `auth.py`    | shared secret clients send as X-API-Key |

Local dev: `main.py` calls `load_dotenv()` (wrapped in try/except ImportError,
so missing python-dotenv degrades gracefully) reading `.env` from cwd.
Container: compose `env_file` injects it; `load_dotenv()` is then a no-op.

## docker

```yaml
compose_file: infra/docker/docker-compose.yml
build_context: ../..                              # repo root, NOT infra/docker
dockerfile: infra/docker/backend/Dockerfile
reason_for_root_context: Dockerfile COPYs apps/backend/, which is outside infra/docker
restart: always
env_file: {path: .env, required: false}            # "load if present" per spec
run: cd infra/docker && docker compose up --build
```

### OPEN ISSUE: invalid network config

```yaml
status: BROKEN as of 2026-10-04
problem: docker-compose.yml declares BOTH `network_mode: host` AND `ports`.
         Docker rejects this: "host" network_mode is incompatible with port_bindings.
context:
  - original spec required `network: host`
  - `network_mode: host` works on LINUX hosts only
  - on macOS/Windows Docker Desktop, host mode attaches the container to the
    Docker Linux VM's network, NOT the host. Requests to localhost:8000 from
    the Mac then fail with "Couldn't connect to server" even though the
    container is listening.
resolution_required: pick ONE
  option_linux_deploy:  keep `network_mode: host`, remove `ports`
  option_portable:      remove `network_mode: host`, keep `ports: ["8000:8000"]`
                        (works on macOS + Linux; deviates from original spec)
owner_decision: PENDING - do not silently pick one; ask.
```

## decisions

| date       | decision                                             | why |
|------------|------------------------------------------------------|-----|
| 2026-10-04 | header name `X-API-Key`                              | conventional for static shared secrets |
| 2026-10-04 | flat imports in backend, no package prefix           | container copies apps/backend/ to /app root |
| 2026-10-04 | compose build context = repo root                    | Dockerfile must reach apps/backend/ |
| 2026-10-04 | `env_file.required: false`                           | spec said load .env "if present" |
| 2026-10-04 | `.env` gitignored, `.env.example` committed          | keep secrets out of VCS |
| 2026-10-04 | python 3.13, port 8000 hardcoded                     | default; not yet externalized |

## verified

```yaml
date: 2026-10-04
method: local uvicorn on 127.0.0.1:8123, curl
results:
  - "GET / no header -> 401"
  - "GET / valid X-API-Key -> 200"
  - "GET /voice/health valid X-API-Key -> 200"
  - "GET /voice/health wrong key -> 401"
caveat: app logic verified OUTSIDE docker. Container networking NOT verified
        (see OPEN ISSUE above). No automated test suite exists yet.
```

## backlog

```yaml
blocking:
  - resolve compose network_mode/ports conflict
unstarted:
  - apps/ui/ - nothing scaffolded, no framework chosen
  - no automated tests (no pytest, no CI)
  - port 8000 and python version are hardcoded, not env-driven
  - single static API key only; no rotation, no per-client keys, no rate limiting
  - voice route has only /health; no real voice functionality
```

## update_protocol

On ANY change to this repo, update the sections that change:

```yaml
always:
  - meta.last_updated -> today's date (absolute, YYYY-MM-DD)
on_new_or_changed_route:   [## routes]
on_new_env_var:            [## env, both .env.example files]
on_new_file_or_dir:        [## layout]
on_dependency_change:      [## stack, requirements.txt]
on_docker_change:          [## docker]
on_architectural_choice:   [## decisions (append row, never rewrite history)]
on_test_or_manual_verify:  [## verified]
on_finishing_backlog_item: [## backlog (remove it), ## verified]
on_discovering_a_defect:   [## docker OPEN ISSUE style block, or ## backlog]

rules:
  - append to `## decisions`; do not delete or edit past rows
  - keep this file factual. no prose, no narration, no persuasion
  - state absolute dates, never "recently" or "last week"
  - if a section would become wrong, fix it rather than leaving it stale
  - if you hit something surprising that cost you time, record it so the next
    agent does not repeat it
```
