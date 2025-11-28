# OTP Auth Service

FastAPI (async) service for user registration and login with 6-digit email OTP. OTPs live in Redis with TTL; users live in PostgreSQL. Frontend: `index.html`.

## Features
- Async FastAPI + SQLAlchemy (asyncpg)
- Redis-backed OTP (auto-expire, single-use)
- SMTP email delivery (no dev shortcuts)
- Clean layering (api/routes, services, db, core)
- One-shot launcher to install the latest CPython, dependencies, Docker containers, and start API

## Requirements
- Python 3.10+ (launcher installs the newest stable CPython version if missing)
- uv (installer handled by launcher if missing)
- Docker (for Postgres/Redis containers)
- SMTP credentials

## Quick start (launcher)
```bash
python launcher.py
```
Add `--auto` to confirm every installation prompt automatically (or include `--python <version>` to pin a specific interpreter).
Launcher flow:
1) Ensures uv and installs the latest stable CPython release that already has asyncpg/other binary wheels (currently capped at the latest supported minor version).
2) Creates or recreates the in-repo `.venv` so the launcher always runs inside the selected Python version.
3) Runs `uv sync --locked --no-install-project --python <python-path>` so dependencies land inside `.venv`.
4) Starts Docker containers for Postgres/Redis (offers alt ports if busy).
5) Runs optional SMTP test email.
6) Applies SQL migrations while running under the uv-managed interpreter so the launcher retains control of every Python step.
7) Starts API on `0.0.0.0:8000` via `uv run --python <python-path> uvicorn app.main:app --reload` so uv always manages the server process.

Logs are prefixed with `[launcher] ...`, so you can quickly understand why anything is installed or rebuilt; the launcher now chooses the latest Python that meets the `>=3.12` spec and caps at 3.12.12 to avoid native rebuilds. It refreshes `uv.lock` automatically before syncing dependencies so lock/state stay aligned.

Launcher prompts before each major install (Python, deps, Docker, SMTP tests) so you can approve the work. If you decline an install, the launcher explains how to provision that component manually and then exits.

The launcher queries `uv python list --output-format json` to detect the newest stable CPython release that matches your OS/architecture and installs that interpreter before syncing dependencies.

By default `python launcher.py` prompts before every installation and automatically picks the newest Python release with prebuilt native wheels (asyncpg, etc.). Pass `--auto` to confirm each step automatically or add `--python <version>` (e.g., `--python 3.13.9` or `--python 3.12`) if you need a specific interpreter while staying in interactive mode.

This project is set up as a uv workspace: `pyproject.toml` was bootstrapped with `uv init --bare --name user-management-with-email-otp` and the dependency lockfile is stored in `uv.lock`, so `uv sync --locked` installs reproducible packages based on that graph.

## Docker / Compose
1) Copy env and fill secrets (DB/Redis URLs are overridden to in-network hosts by compose):
```bash
cp .env.example .env
# set SECRET_KEY/SMTP_*/ADMIN_* and any OAuth keys
```
2) Build and start everything (API + Postgres + Redis):
```bash
docker compose up --build
```
3) API available on http://127.0.0.1:8000 (Swagger at `/docs`).
4) Stop stack:
```bash
docker compose down
```

## Manual setup
1) Ensure a Python interpreter is available through uv (launcher downloads the latest stable CPython, or run `uv python install 3.15.0`/`uv python install 3` if you want a specific release).
2) Sync dependencies defined in `pyproject.toml` into that interpreter:
```bash
uv sync --python <python-path> --locked --no-install-project
```
Replace `<python-path>` with the uv-managed interpreter you intend to run (the path reported by `uv python find <version>` or visible via `uv python list --only-installed --output-format json`).
To run without prompts use `--auto`; combine with `--python <version>` when you want to fix the interpreter version while still running unattended.
3) Windows-only: the launcher detects whether `cl.exe` exists and offers to install the Microsoft Visual C++ Build Tools via `winget` before syncing dependencies so packages such as `asyncpg` can compile. If you decline or the install fails, the launcher instructs you to install them manually from https://visualstudio.microsoft.com/visual-cpp-build-tools/.
3) Environment
```bash
cp .env.example .env
```
Fill:
 ```
 DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/user_management
 REDIS_URL=redis://localhost:6379/0
 SECRET_KEY=replace-with-strong-random
 ACCESS_TOKEN_EXPIRE_MINUTES=30
 OTP_EXPIRE_SECONDS=120
 OTP_LENGTH=6
 SMTP_SERVER=smtp.gmail.com
 SMTP_PORT=587
 SMTP_USERNAME=you@example.com
 SMTP_PASSWORD=app_password
 FROM_EMAIL=you@example.com
 ```
3) Run containers (if not using external services)
```bash
docker run -d --name usermgmt-postgres \
  -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=user_management \
  -p 5432:5432 -v usermgmt-postgres-data:/var/lib/postgresql/data \
  postgres:16-alpine

docker run -d --name usermgmt-redis \
  -p 6379:6379 -v usermgmt-redis-data:/data \
  redis:7-alpine
```
4) Start API
```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
Swagger: http://127.0.0.1:8000/docs

## Project structure
- `app/main.py` - FastAPI app, router include, CORS, lifespan
- `app/api/routes/auth.py` - register, verify-otp, resend-otp, login
- `app/services/auth.py` - business logic; uses `OTPService` + email sender
- `app/services/otp.py` - Redis OTP issue/validate/invalidate
- `app/services/email.py` - SMTP email sending
- `app/db/session.py` - async engine/session (asyncpg)
- `app/db/models` - SQLAlchemy models (User)
- `app/core/config.py` - settings via pydantic-settings
- `index.html` - minimal frontend (register/login/OTP)

## API overview
- `POST /auth/register` - body `{email, password}`; sends OTP; user inactive until verify
- `POST /auth/verify-otp` - `{email, code}`; marks user verified/active
- `POST /auth/resend-otp` - `{email}`; sends new OTP
- `POST /auth/login` - `{email, password}`; requires verified user; returns `{access_token, token_type}`
- `GET /auth/oauth/{provider}/start` - returns `auth_url` + `state` for Google/GitHub
- `POST /auth/oauth/{provider}/callback` - `{code, state, redirect_uri?}`; returns `{access_token, token_type, provider}`
- OTP re-check: after `ACCESS_TOKEN_EXPIRE_MINUTES`, a fresh OTP is emailed on next login attempt; verification is required again before issuing a new token

### OAuth notes
- Providers: `google`, `github`
- Required env keys: `GOOGLE_CLIENT_ID/SECRET/REDIRECT_URI`, `GITHUB_CLIENT_ID/SECRET/REDIRECT_URI`
- The backend signs `state` with `SECRET_KEY` (TTL: `OAUTH_STATE_TTL_SECONDS`, default 600s)
- Suggested redirect URI for local static frontend: `http://127.0.0.1:5500/index.html`
- Flow: frontend calls `/auth/oauth/{provider}/start` to get `auth_url`, browser redirects to provider, provider returns `code/state` to the redirect URI, frontend POSTs to `/auth/oauth/{provider}/callback`

### How to fill new .env OAuth variables
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`: create a Google Cloud OAuth 2.0 Client ID (application type: Web), add Authorized redirect URI `http://127.0.0.1:5500/index.html`, copy the client ID/secret.
- `GOOGLE_REDIRECT_URI`: match the redirect above (e.g., `http://127.0.0.1:5500/index.html`).
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`: GitHub Settings → Developer settings → OAuth Apps → New OAuth App. Homepage: your frontend origin (e.g., `http://127.0.0.1:5500`). Authorization callback URL: `http://127.0.0.1:5500/index.html`. Copy the generated ID/secret.
- `GITHUB_REDIRECT_URI`: same as the GitHub callback URL (`http://127.0.0.1:5500/index.html`).

## Frontend
- Serve: `python -m http.server 5500` then open http://127.0.0.1:5500/index.html
- Uses `API_BASE = http://127.0.0.1:8000` (adjust if needed)
- OTP inputs auto-advance; Enter on last digit submits; password fields have show/hide toggle

## Tips
- SMTP: Use correct `FROM_EMAIL`/`SMTP_USERNAME`, App Password for Gmail, check spam.
- Ports busy- Launcher suggests alternatives and can update `.env`.
- OTP expires after `OTP_EXPIRE_SECONDS`; resend to refresh.

### Dependency updates
Add or remove packages in `pyproject.toml`, then regenerate the lockfile with `uv lock --python <python>` and re-run `uv sync --python <python-path> --locked --no-install-project`. Committing the updated `uv.lock` keeps the launcher, Docker image, and teammates aligned with the same versions.

## Troubleshooting
- Email not delivered: check SMTP creds, spam folder, and API response `detail` if send fails.
- 400 on register/login: read `detail` (duplicate email, invalid creds, unverified email).
- Redis/Postgres errors: confirm containers up and URLs correct in `.env`.
