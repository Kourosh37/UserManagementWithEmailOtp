# OTP Auth Service

FastAPI (async) service for user registration and login with 6-digit email OTP. OTPs live in Redis with TTL; users live in PostgreSQL. Frontend: `index.html`.

## Features
- Async FastAPI + SQLAlchemy (asyncpg)
- Redis-backed OTP (auto-expire, single-use)
- SMTP email delivery (no dev shortcuts)
- Clean layering (api/routes, services, db, core)
- One-shot launcher to install Python 3.12, deps, Docker containers, and start API

## Requirements
- Python 3.10+ (Python 3.12.x recommended; launcher installs it if missing)
- uv (installer handled by launcher if missing)
- Docker (for Postgres/Redis containers)
- SMTP credentials

## Quick start (launcher)
```bash
python launcher.py
```
Launcher flow:
1) Ensures uv; installs Python 3.12 if needed.
2) Creates `.venv` with that Python (recreates if wrong version).
3) Installs deps with `uv pip`.
4) Starts Docker containers for Postgres/Redis (offers alt ports if busy).
5) Runs optional SMTP test email.
6) Starts API on `0.0.0.0:8000`.

## Manual setup
1) Create venv and install deps
```bash
uv venv
uv pip install -r requirements.txt
```
2) Environment
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

## Frontend
- Serve: `python -m http.server 5500` then open http://127.0.0.1:5500/index.html
- Uses `API_BASE = http://127.0.0.1:8000` (adjust if needed)
- OTP inputs auto-advance; Enter on last digit submits; password fields have show/hide toggle

## Tips
- SMTP: Use correct `FROM_EMAIL`/`SMTP_USERNAME`, App Password for Gmail, check spam.
- Ports busy- Launcher suggests alternatives and can update `.env`.
- OTP expires after `OTP_EXPIRE_SECONDS`; resend to refresh.

## Troubleshooting
- Email not delivered: check SMTP creds, spam folder, and API response `detail` if send fails.
- 400 on register/login: read `detail` (duplicate email, invalid creds, unverified email).
- Redis/Postgres errors: confirm containers up and URLs correct in `.env`.
