# Containerized Deployment Bootstrap Design

## Problem

The repository currently assumes a host-managed development environment:

- backend commands are documented around `uv`
- frontend setup is documented around local `pnpm` installation
- startup relies on local shell scripts under `scripts/startup/`
- there is no official containerized deployment path
- there is no automated cross-platform verification for Docker-based startup on Windows, macOS, and Linux

That leaves two gaps:

- users who want a safe, one-command deployment still need to modify their host environment manually
- the project has no stable, production-like packaging contract that can be validated consistently across operating systems

## Goal

Add an official containerized deployment path that is safe for host machines, close to real deployment topology, and verifiable on Windows, macOS, and Linux without requiring host-side installation of `uv`, Node.js, or pnpm.

## Decisions Already Locked

The design below reflects the confirmed decisions from the discussion:

- official deployment path is containerized only
- local/native development remains supported through existing `scripts/startup/*` scripts
- native setup is documented only; no host-mutating bootstrap script will be added
- Redis is a hard dependency for the containerized stack
- MCP servers run as independent containers, not as sidecars inside the API container
- deployment entrypoints are both supported:
  - raw `docker compose`
  - lightweight repository wrapper scripts
- cross-platform verification must include Windows, macOS, and Linux
- development workflow remains local via `scripts/`, not Docker-first

## Scope

In scope:

- add production-like Docker packaging for:
  - frontend
  - FastAPI API
  - market-data MCP server
  - news-search MCP server
  - Redis
- add a default `docker compose` stack for the five services above
- add repository wrapper scripts for starting, stopping, and smoke-checking the container stack
- add container-specific documentation and environment guidance
- add automated cross-platform verification for Docker compose startup and health checks
- add a local smoke-check entrypoint for humans to validate the stack after startup

Out of scope:

- replacing local development scripts with Docker-based development
- automatically installing Docker, `uv`, Node.js, pnpm, or any other host dependency
- Kubernetes, Helm, Nomad, or VM image packaging
- fully reproducing external providers in containers (for example, mock Tavily/OpenAI services)
- converting native startup scripts into cross-platform wrappers

## Approach Options

### Option 1: Single application container plus frontend and Redis

Package the API and both MCP servers into one Python image, run them as multiple processes in one container, and keep only `frontend` and `redis` as separate services.

Pros:

- fewer Dockerfiles
- fewer compose services

Cons:

- weak process isolation
- harder health checks and restart behavior
- logs from different backend processes get mixed
- diverges from the repository's current architecture

### Option 2: Independent service containers with one production-like compose stack

Package each runtime service independently:

- `frontend`
- `api`
- `market-data-mcp`
- `news-search-mcp`
- `redis`

Provide one official compose stack and thin wrapper scripts around it.

Pros:

- matches the current architecture and service boundaries
- makes health checks and dependency ordering explicit
- easiest to debug and monitor
- easiest to validate consistently in CI

Cons:

- more files to maintain
- initial Docker setup is more verbose

### Option 3: Independent containers with compose profiles for multiple deployment modes

Start from Option 2, but add `profiles` for variants like `backend-only`, `full`, and `ops`.

Pros:

- flexible for future deployment modes

Cons:

- more complexity than the current requirement needs
- higher risk of fragmented testing paths

## Recommendation

Adopt Option 2.

It is the smallest design that still preserves the real service topology, satisfies the confirmed Redis and MCP isolation requirements, and gives the repository a single stable container deployment contract that CI can verify across operating systems.

## Architecture

The official deployment stack will contain exactly five services:

1. `redis`
2. `market-data-mcp`
3. `news-search-mcp`
4. `api`
5. `frontend`

### Service relationships

- `api` depends on healthy `redis`
- `api` depends on healthy `market-data-mcp`
- `api` depends on healthy `news-search-mcp`
- `frontend` depends on healthy `api`

### Network model

All services run on a shared compose network.

Internal service discovery uses compose service names:

- Redis: `redis:6379`
- Market MCP: `http://market-data-mcp:8000/mcp`
- News MCP: `http://news-search-mcp:8001/mcp`

Browser-facing access stays on host-local ports:

- frontend: `http://localhost:3000`
- api: `http://localhost:8080`
- market-data MCP health: `http://localhost:8000/health`
- news-search MCP health: `http://localhost:8001/health`

### Runtime contract

The containerized stack is intended to be production-like, not development-live-reload:

- Python services run without `--reload`
- frontend uses a production build and `pnpm start`
- Redis uses a named volume for persistence
- failure to start Redis or either MCP service blocks the API from reaching ready state

## Container Packaging Design

### Python images

Add a shared Python container strategy for `api`, `market-data-mcp`, and `news-search-mcp`:

- base image: slim Python 3.13 image
- copy `uv` into the image from the official Astral `uv` container image instead of installing it with ad-hoc curl logic
- copy dependency manifests first for build cache efficiency
- install backend dependencies from project metadata with frozen `uv` resolution during image build
- copy the repository source
- set a stable working directory inside the container

Each Python service gets its own Dockerfile or a shared base plus service-specific final stages. The important contract is independent images and independent commands, not a single multi-process container.

### Frontend image

Use a Node image with `corepack` and `pnpm` enabled:

- install frontend dependencies from `frontend/package.json` and lockfile
- build the Next.js application
- run production server on `0.0.0.0:3000`

The frontend image should not depend on host-installed pnpm.

### Redis image

Use the official Redis image with:

- a named volume for data
- an explicit health check
- no fallback mode in compose
- no bind mount for the Redis data directory, to avoid host permission drift on Linux

## Compose Design

Add a top-level compose file for the official stack.

Expected characteristics:

- explicit service names matching the architecture
- health checks for all runtime services
- `depends_on` with health conditions where supported
- named volume for Redis data
- env-file driven configuration
- stable port mapping for host access

### Health check contract

Use existing endpoints where they already exist:

- API: `GET /api/health`
- Market MCP: `GET /health`
- News MCP: `GET /health`
- Redis: `redis-cli ping`
- Frontend: HTTP check against `/`

### Environment mapping

The compose stack must override host-local defaults with container-safe values where required.

Important examples:

- API service:
  - `REDIS_URL=redis://redis:6379/0`
  - `REDIS_ENABLED=true`
  - `MCP_MARKET_DATA_URL=http://market-data-mcp:8000/mcp`
  - `MCP_NEWS_SEARCH_URL=http://news-search-mcp:8001/mcp`
- Frontend service:
  - `NEXT_PUBLIC_API_URL=http://localhost:8080`

The frontend variable remains `localhost` because it is consumed by the browser, not by container-to-container traffic.

### Frontend networking contract

The current frontend codebase consumes `@/lib/api` from client components and client pages, so a browser-facing `NEXT_PUBLIC_API_URL=http://localhost:8080` is correct for the current deployment behavior.

However, this must not become an undocumented assumption for future frontend changes. If the implementation work discovers existing server-side fetches, or if the containerization work introduces SSR/RSC/API-route fetches as part of the deployment path, the frontend runtime must also support an internal server-side API target such as:

- `INTERNAL_API_URL=http://api:8080`

The implementation plan should choose one consistent strategy for server-side access if it becomes necessary:

- add a dedicated internal server-side API base URL
- or add a deliberate Next.js rewrite/proxy layer

The initial container deployment work should not broaden into a frontend proxy refactor unless server-side API access is actually required by the current codepath.

## Wrapper Script Design

Provide thin repository-owned wrappers around compose rather than host-mutating bootstrap logic.

### Required scripts

- `scripts/deploy/start_container_stack.sh`
- `scripts/deploy/stop_container_stack.sh`
- `scripts/deploy/smoke_test_container_stack.sh`
- `scripts/deploy/start_container_stack.ps1`
- `scripts/deploy/stop_container_stack.ps1`
- `scripts/deploy/smoke_test_container_stack.ps1`

### Why both `.sh` and `.ps1`

Claiming Windows support with only a shell wrapper would be incomplete because many Windows users run Docker Desktop without Git Bash or WSL. The official entrypoint therefore needs a native Windows wrapper alongside the Unix shell wrapper.

### Wrapper responsibilities

Wrappers may:

- check that Docker is installed
- check that `docker compose` is available
- fail fast when `.env` is missing, with an explicit message to copy `.env.example` and fill required keys
- check that required env files exist
- call `docker compose up -d --build`
- wait for service health
- print URLs and troubleshooting hints

Wrappers must not:

- install host software
- rewrite host shell profiles
- change system package manager state
- silently mutate `.env`

### Raw compose remains first-class

Documentation must also show the equivalent native Docker commands so the wrappers are convenience tools, not the only supported entrypoint.

## Environment File Strategy

Keep the existing `.env.example` for general repository setup, but add deployment-focused guidance so container users can create a container-ready `.env` without guessing internal service URLs.

The simplest acceptable design is:

- keep one `.env.example`
- update comments to distinguish:
  - local/native values
  - compose-managed values
- let compose inject service-specific overrides for container-only addresses

If the implementation becomes hard to reason about with one file, introduce a dedicated deployment example file such as `.env.container.example`. The implementation plan should choose the simpler path after checking actual compose ergonomics.

## Documentation Design

Update repository documentation so deployment and development are clearly separated.

### Deployment docs must cover

- prerequisites: Docker and Docker Compose only
- Docker Desktop / OrbStack resource guidance for macOS and Windows, including a concrete memory recommendation such as 4 GB minimum and 8 GB preferred because the five-service stack can fail with opaque OOM symptoms under low VM memory
- how to create `.env`
- how to start via raw compose
- how to start via wrapper script
- how to stop the stack
- how to run smoke checks
- service URLs
- persistence behavior for Redis
- common failures:
  - missing API keys
  - port conflicts
  - Docker daemon unavailable
  - Docker Desktop / OrbStack memory too low for image build or startup
  - failed health checks

### Native development docs must remain

Native setup stays documented as a manual path using:

- `uv sync`
- frontend package installation
- existing `scripts/startup/*`

But it should be described as development-oriented, not as the recommended deployment route.

## Cross-Platform Verification Design

### CI verification

Add a CI workflow with an OS matrix:

- Linux
- macOS
- Windows

Each matrix job should validate the container stack contract at a minimum by running:

1. compose syntax / resolution check
2. image build
3. detached startup
4. health polling for all services
5. smoke requests against host-exposed endpoints
6. teardown

Minimum smoke assertions:

- `GET http://localhost:8080/api/health` returns healthy
- `GET http://localhost:8000/health` returns ok
- `GET http://localhost:8001/health` returns ok
- `GET http://localhost:3000/` returns success

### Repository-local smoke scripts

The `smoke_test_container_stack` wrappers should be usable outside CI and should:

- verify all containers are running
- verify all health endpoints respond
- surface failing service names clearly

This gives maintainers a reproducible local validation path without requiring them to reconstruct CI commands manually.

## Testing Strategy

Testing should cover three layers.

### Layer 1: Static verification

- compose file resolves successfully
- wrapper scripts have basic argument and file-path tests where practical
- documentation references real script paths and commands

### Layer 2: Runtime smoke verification

- stack builds successfully
- stack starts successfully
- all services become healthy
- frontend can reach backend through the documented public URL contract

### Layer 3: Cross-platform verification

- the same smoke workflow passes on Windows, macOS, and Linux runners

This design intentionally does not require full application integration tests in the container matrix. The first objective is to prove packaging and startup portability.

## Risks and Mitigations

- Risk: frontend uses the wrong API base URL inside the browser
  - Mitigation: document and enforce that `NEXT_PUBLIC_API_URL` for the containerized frontend must stay host-reachable, not container-internal

- Risk: compose startup appears healthy before dependent services are truly ready
  - Mitigation: add real HTTP health checks for API and MCP services, and gate dependent services on health where compose supports it

- Risk: Redis fallback semantics hide packaging mistakes
  - Mitigation: treat Redis as a hard dependency in compose and fail health/startup when it is unavailable

- Risk: Windows support is nominal only
  - Mitigation: provide native PowerShell wrappers and include Windows in CI matrix verification

- Risk: macOS or Windows users hit opaque Docker Desktop / OrbStack OOM failures during build or startup
  - Mitigation: document minimum VM memory expectations prominently in deployment instructions and troubleshooting guidance

- Risk: a future frontend SSR/RSC path tries to call `http://localhost:8080` from inside the frontend container
  - Mitigation: treat browser-facing and server-side frontend API targets as separate concerns, and add an internal API URL or explicit rewrite strategy if server-side access is introduced

- Risk: documentation drifts from real commands
  - Mitigation: verify wrapper paths and compose commands in automated checks where possible

## Acceptance Criteria

- the repository contains an official production-like Docker compose stack for `frontend`, `api`, `market-data-mcp`, `news-search-mcp`, and `redis`
- Redis is a hard dependency in the deployment path
- MCP servers run as independent services in the compose topology
- the repository provides both raw compose instructions and wrapper scripts for container deployment
- wrapper scripts exist for Unix-like shells and PowerShell
- deployment wrappers do not install or mutate host dependencies
- repository docs clearly separate containerized deployment from native development
- CI validates compose startup and health checks on Windows, macOS, and Linux
- a maintainer can run a local smoke check against the containerized stack using repository scripts
