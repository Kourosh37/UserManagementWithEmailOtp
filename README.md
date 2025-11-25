# User Management with Email OTP

FastAPI service for registering and logging in users with a 6-digit email OTP. A simple HTML page (`index.html`) is included to drive the flow.

## Prerequisites
- Python 3.10+ with `pip`
- PostgreSQL running locally or reachable over the network
- SMTP credentials (Gmail, Outlook, Mailtrap, etc.)
- Terminal access to the project root (`{root}\UserManagementWithEmailOtp`)

## Setup

### 1) Create and activate a virtual environment
```powershell
cd {root}\UserManagementWithEmailOtp
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate    # macOS/Linux
```

### 2) Install dependencies
```bash
pip install -r requirement.txt
```

### 3) Create and fill `.env`
Copy the template and edit it:
```powershell
copy .env.example .env        # Windows
# cp .env.example .env        # macOS/Linux
```

Recommended values (edit to your environment):
```
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/user_management
SECRET_KEY=replace-with-a-strong-random-string
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your@email.com
SMTP_PASSWORD=your_app_password_or_smtp_password
FROM_EMAIL=your@email.com
ENVIRONMENT=development
```
- `SECRET_KEY`: generate one with `python -c "import secrets; print(secrets.token_hex(32))"`.
- `ENVIRONMENT=development` prints OTP codes to the API console instead of sending emails. Remove or change it when you want real emails.

### 4) Prepare PostgreSQL
1. Start PostgreSQL.
2. Create a database (example):
   ```bash
   psql -U postgres -h localhost -c "CREATE DATABASE user_management;"
   ```
3. Update `DATABASE_URL` in `.env` to match your DB name, user, password, and host.

Tables are created automatically on API startup (`models.Base.metadata.create_all`).

### 5) Run the API server
With the virtual environment active and from the project root:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- Swagger UI: `http://127.0.0.1:8000/docs`
- OTP codes are logged here when `ENVIRONMENT=development`.

### 6) Serve the UI
The API allows requests from `http://127.0.0.1:5500` and `http://localhost:5500`. From the project root, serve the static files:
```bash
python -m http.server 5500
```
Open `http://127.0.0.1:5500/index.html` in your browser while the API is running.

### 7) Use the UI
- Register with an email and password; an OTP is emailed or printed in the API console.
- Enter the 6-digit OTP to verify the account.
- Log in with the same email/password to get an access token shown on the dashboard.
- If the code expires (default 10 minutes), click "Resend Code" to get a new one.

## Common commands (project root)
- Activate venv (Windows): `.\venv\Scripts\activate`
- Activate venv (macOS/Linux): `source venv/bin/activate`
- Install deps: `pip install -r requirement.txt`
- Start API: `uvicorn app.main:app --reload`
- Serve UI: `python -m http.server 5500`

## SMTP tips
- Gmail: `SMTP_SERVER=smtp.gmail.com`, `SMTP_PORT=587`, use an App Password if 2FA is on.
- Mailtrap or other providers: use the host/port/user/password they provide.
- `FROM_EMAIL` should be an address allowed by your SMTP provider.

## Troubleshooting
- Database connection errors: confirm PostgreSQL is running and `DATABASE_URL` is correct.
- OTP not delivered: verify SMTP credentials or use `ENVIRONMENT=development` to read the code in the console.
- CORS issues: serve the UI on port 5500 as shown, or add your origin in `app/main.py` under `allow_origins`.
