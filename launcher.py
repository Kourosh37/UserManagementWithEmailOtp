"""One-shot launcher to set up Python, virtual env, containers, and the API."""

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

ROOT = Path(__file__).parent.resolve()
ENV_FILE = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
VENV_DIR = ROOT / ".venv"


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Console prompt that returns a boolean while handling default answers."""
    default_text = "[Y/n]" if default else "[y/N]"
    while True:
        choice = input(f"{question} {default_text} ").strip().lower()
        if not choice:
            return default
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False
        print("Please respond with 'y' or 'n'.")


def run(cmd, check=True, capture_output=False):
    """Wrapper around subprocess.run that echoes the command for transparency."""
    print(f"> {' '.join(cmd)}")
    return subprocess.run(cmd, check=check, capture_output=capture_output, text=True)


def ensure_uv():
    """Ensure the `uv` tool is installed; optionally install it via pip."""
    uv_cmd = shutil.which("uv")
    if uv_cmd:
        return uv_cmd
    if not prompt_yes_no("uv not found. Install via pip?", default=True):
        raise RuntimeError("uv is required. Aborting because installation was declined.")
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    run([sys.executable, "-m", "pip", "install", "uv"])
    uv_cmd = shutil.which("uv")
    if not uv_cmd:
        raise RuntimeError("uv installation failed. Please install uv manually and retry.")
    return uv_cmd


def try_capture(cmd):
    """Run a command and swallow errors, returning None if execution fails."""
    try:
        return run(cmd, capture_output=True)
    except Exception:
        return None


def find_python_path(version: str = "3.12", uv_cmd: str | None = None) -> str | None:
    """Find a Python interpreter matching the requested version.

    The search order tries the Windows py launcher, direct pythonX.Y calls, uv
    managed interpreters, and common install locations on different platforms.
    """
    # Try Windows py launcher
    result = try_capture(["py", f"-{version}", "-c", "import sys; print(sys.executable)"])
    if result and result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    # Try direct python command
    result = try_capture([f"python{version}", "-c", "import sys; print(sys.executable)"])
    if result and result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    # Try uv-managed interpreters list
    if uv_cmd:
        result = try_capture([uv_cmd, "python", "find", version])
        if result and result.returncode == 0 and result.stdout.strip():
            path = result.stdout.strip().splitlines()[-1].strip()
            if path:
                return path

        result = try_capture([uv_cmd, "python", "list", "--format", "json"])
        if result and result.returncode == 0 and result.stdout:
            try:
                py_list = json.loads(result.stdout)
                # py_list is an array of dicts; pick latest matching major.minor
                matching = [
                    p for p in py_list if str(p.get("version", "")).startswith(version)
                ]
                # fall back to any that has major.minor
                if not matching:
                    matching = [
                        p for p in py_list if version in str(p.get("version", ""))
                    ]
                if matching:
                    # choose first entry's executable
                    exe = matching[0].get("executable")
                    if exe:
                        return exe
            except Exception:
                pass

    # Try default uv install location search
    local_app = Path(os.getenv("LOCALAPPDATA", "")) / "uv" / "python"
    xdg_home = Path(os.path.expanduser("~")) / ".local" / "share" / "uv" / "python"
    home_local = Path(os.path.expanduser("~")) / ".local" / "python"
    for base in [local_app, xdg_home, home_local]:
        if base.exists():
            candidates = sorted(base.glob(f"**/*{version}*/python*.exe" if os.name == "nt" else f"**/*{version}*/python*"), reverse=True)
            for cand in candidates:
                if cand.is_file():
                    return str(cand)
    return None


def ensure_python(version: str, uv_cmd: str) -> str:
    """Return an interpreter path, installing with uv if not present."""
    path = find_python_path(version, uv_cmd)
    if path:
        print(f"Using Python {version} at: {path}")
        return path
    print(f"Python {version} not found. Installing via uv ...")
    run([uv_cmd, "python", "install", version])
    path = find_python_path(version, uv_cmd)
    if not path:
        raise RuntimeError(
            f"Failed to install Python {version}. If uv installed it, ensure its install dir is on PATH "
            f"or rerun launcher. Check ~/.local/python or %LOCALAPPDATA%/uv/python."
        )
    print(f"Installed Python {version} at: {path}")
    return path


def ensure_env_file():
    """Create a .env from .env.example if missing so the app can start."""
    if ENV_FILE.exists():
        return
    if ENV_EXAMPLE.exists() and prompt_yes_no("No .env found. Copy from .env.example?", default=True):
        ENV_FILE.write_text(ENV_EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        print("Created .env from .env.example")
    else:
        print("No .env present. You should create one to match your database/redis/SMTP settings.")


def parse_env():
    """Parse key/value pairs from the .env file into a dictionary."""
    data = {}
    if not ENV_FILE.exists():
        return data
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


def report_env_gaps(env):
    """Warn about missing required or SMTP-related environment keys."""
    required_keys = ["DATABASE_URL", "REDIS_URL", "SECRET_KEY"]
    missing = [k for k in required_keys if not env.get(k)]
    if missing:
        print(f"Warning: Missing/empty keys in .env: {', '.join(missing)}")
        print("Update .env before running in production.")
    smtp_keys = ["SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "FROM_EMAIL"]
    smtp_missing = [k for k in smtp_keys if not env.get(k)]
    if smtp_missing:
        print(f"Warning: Missing/empty SMTP keys for email sending: {', '.join(smtp_missing)}")


def parse_database_settings(env):
    """Break down the database URL for container creation defaults."""
    db_url = env.get(
        "DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/user_management",
    )
    parsed = urlparse(db_url)
    user = parsed.username or "postgres"
    password = parsed.password or "postgres"
    db_name = parsed.path.lstrip("/") or "user_management"
    port = parsed.port or 5432
    return {"user": user, "password": password, "db": db_name, "port": port}


def parse_redis_settings(env):
    """Extract host port from the Redis URL for container startup."""
    redis_url = env.get("REDIS_URL", "redis://localhost:6379/0")
    parsed = urlparse(redis_url)
    port = parsed.port or 6379
    return {"port": port}


def port_available(port: int) -> bool:
    """Check whether a TCP port can be bound (used before starting containers)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", port))
            return True
        except OSError:
            return False


def find_free_port(start_port: int, limit: int = 20) -> int | None:
    """Find the first available port in a consecutive range starting at start_port."""
    for p in range(start_port, start_port + limit):
        if port_available(p):
            return p
    return None


def update_env_database_port(env: dict, new_port: int):
    """Update DATABASE_URL in .env to point at a new local port."""
    if not ENV_FILE.exists():
        return
    db_url = env.get("DATABASE_URL")
    if not db_url:
        return
    parsed = urlparse(db_url)
    userinfo = ""
    if parsed.username:
        userinfo = parsed.username
        if parsed.password:
            userinfo += f":{parsed.password}"
        userinfo += "@"
    host = parsed.hostname or "localhost"
    new_netloc = f"{userinfo}{host}:{new_port}"
    new_url = urlunparse(
        (parsed.scheme, new_netloc, parsed.path or "", parsed.params, parsed.query, parsed.fragment)
    )

    lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    new_lines = []
    replaced = False
    for line in lines:
        if line.startswith("DATABASE_URL="):
            new_lines.append(f"DATABASE_URL={new_url}")
            replaced = True
        else:
            new_lines.append(line)
    if not replaced:
        new_lines.append(f"DATABASE_URL={new_url}")
    ENV_FILE.write_text("\n".join(new_lines) + ("\n" if new_lines and new_lines[-1] else ""), encoding="utf-8")
    env["DATABASE_URL"] = new_url


def ensure_venv(uv_cmd):
    """Return True if the virtual environment already exists."""
    return VENV_DIR.exists()


def create_venv(uv_cmd: str, python_path: str):
    """Create a new virtual environment with uv."""
    run([uv_cmd, "venv", "--python", python_path])


def venv_python() -> Path:
    """Return the path to the venv's python executable on this OS."""
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def venv_python_matches(version: str) -> bool:
    """Verify the venv python version matches the target major.minor."""
    py = venv_python()
    if not py.exists():
        return False
    result = try_capture([str(py), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"])
    return bool(result and result.returncode == 0 and result.stdout.strip().startswith(version))


def recreate_venv(uv_cmd: str, python_path: str):
    """Delete and recreate the venv (used when the version is mismatched)."""
    if VENV_DIR.exists():
        shutil.rmtree(VENV_DIR)
    create_venv(uv_cmd, python_path)


def install_dependencies(uv_cmd, python_path: str):
    """Install requirements into the venv using uv pip after user confirmation."""
    if prompt_yes_no("Install project dependencies with uv pip?", default=True):
        run([uv_cmd, "pip", "install", "--python", python_path, "-r", "requirements.txt"])


def docker_available():
    """Return True if Docker CLI is on PATH (daemon may still be stopped)."""
    return shutil.which("docker") is not None


def install_docker():
    """Offer to install Docker using a platform-appropriate command."""
    system = platform.system()
    if system == "Windows":
        cmd = ["winget", "install", "-e", "--id", "Docker.DockerDesktop"]
    elif system == "Darwin":
        cmd = ["brew", "install", "--cask", "docker"]
    else:
        cmd = ["sh", "-c", "curl -fsSL https://get.docker.com | sh"]

    if prompt_yes_no(f"Docker not found. Install Docker now using: {' '.join(cmd)} ?", default=False):
        run(cmd, check=False)
        print("Docker install attempted. If this is the first install, ensure the daemon is running and restart your shell if needed.")
    else:
        print("Docker installation skipped. Containers will not be started.")


def container_exists(name):
    """Check whether a Docker container by the given name already exists."""
    try:
        result = run(["docker", "ps", "-a", "--format", "{{.Names}}"], capture_output=True)
        return name in result.stdout.splitlines()
    except Exception:
        return False


def container_running(name):
    """Check whether a Docker container by the given name is currently running."""
    try:
        result = run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True)
        return name in result.stdout.splitlines()
    except Exception:
        return False


def ensure_postgres_container(cfg, env: dict):
    """Create or start the PostgreSQL Docker container based on env config.

    Relies on `port_available` and `find_free_port` to avoid conflicts and
    optionally rewrites DATABASE_URL when a new port is chosen.
    """
    name = "usermgmt-postgres"
    if not docker_available():
        print("Docker not available; skipping PostgreSQL container.")
        return
    if container_running(name):
        print("PostgreSQL container already running.")
        return
    if container_exists(name):
        if prompt_yes_no(f"Start existing PostgreSQL container '{name}'?", default=True):
            run(["docker", "start", name], check=False)
        return
    desired_port = cfg["port"]
    actual_port = desired_port
    if not port_available(desired_port):
        alt = find_free_port(desired_port + 1, limit=20)
        if alt:
            if prompt_yes_no(f"Port {desired_port} is in use. Use {alt} instead?", default=True):
                actual_port = alt
                cfg["port"] = alt
            else:
                print("Port conflict unresolved; skipping PostgreSQL container.")
                return
        else:
            print("No free port found for PostgreSQL in the next 20 ports; skipping container.")
            return

    if prompt_yes_no(f"Create and start PostgreSQL container with Docker on host port {actual_port}?", default=True):
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "-e",
                f"POSTGRES_USER={cfg['user']}",
                "-e",
                f"POSTGRES_PASSWORD={cfg['password']}",
                "-e",
                f"POSTGRES_DB={cfg['db']}",
                "-p",
                f"{actual_port}:5432",
                "-v",
                f"{name}-data:/var/lib/postgresql/data",
                "postgres:16-alpine",
            ]
        )
        if env.get("DATABASE_URL") and actual_port != desired_port:
            if prompt_yes_no(f"Update DATABASE_URL port in .env to {actual_port}?", default=True):
                update_env_database_port(env, actual_port)


def ensure_redis_container(cfg, env: dict):
    """Create or start the Redis Docker container based on env config."""
    name = "usermgmt-redis"
    if not docker_available():
        print("Docker not available; skipping Redis container.")
        return
    if container_running(name):
        print("Redis container already running.")
        return
    if container_exists(name):
        if prompt_yes_no(f"Start existing Redis container '{name}'?", default=True):
            run(["docker", "start", name], check=False)
        return
    desired_port = cfg["port"]
    actual_port = desired_port
    if not port_available(desired_port):
        alt = find_free_port(desired_port + 1, limit=20)
        if alt:
            if prompt_yes_no(f"Port {desired_port} is in use. Use {alt} instead?", default=True):
                actual_port = alt
                cfg["port"] = alt
            else:
                print("Port conflict unresolved; skipping Redis container.")
                return
        else:
            print("No free port found for Redis in the next 20 ports; skipping container.")
            return

    if prompt_yes_no(f"Create and start Redis container with Docker on host port {actual_port}?", default=True):
        run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "-p",
                f"{actual_port}:6379",
                "-v",
                f"{name}-data:/data",
                "redis:7-alpine",
            ]
        )
        if env.get("REDIS_URL") and actual_port != desired_port:
            if prompt_yes_no(f"Update REDIS_URL port in .env to {actual_port}?", default=True):
                # simple replace in .env for port
                lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
                parsed = urlparse(env.get("REDIS_URL"))
                userinfo = ""
                if parsed.username:
                    userinfo = parsed.username
                    if parsed.password:
                        userinfo += f":{parsed.password}"
                    userinfo += "@"
                host = parsed.hostname or "localhost"
                new_url = urlunparse(
                    (
                        parsed.scheme,
                        f"{userinfo}{host}:{actual_port}",
                        parsed.path or "",
                        parsed.params,
                        parsed.query,
                        parsed.fragment,
                    )
                )
                new_lines = []
                replaced = False
                for line in lines:
                    if line.startswith("REDIS_URL="):
                        new_lines.append(f"REDIS_URL={new_url}")
                        replaced = True
                    else:
                        new_lines.append(line)
                if not replaced:
                    new_lines.append(f"REDIS_URL={new_url}")
                ENV_FILE.write_text("\n".join(new_lines) + ("\n" if new_lines and new_lines[-1] else ""), encoding="utf-8")
                env["REDIS_URL"] = new_url


def test_smtp(env: dict):
    """Optional interactive SMTP connectivity test using .env credentials."""
    smtp_server = env.get("SMTP_SERVER")
    smtp_port = int(env.get("SMTP_PORT", "0") or 0)
    smtp_user = env.get("SMTP_USERNAME")
    smtp_password = env.get("SMTP_PASSWORD")
    from_email = env.get("FROM_EMAIL") or smtp_user
    to_email = env.get("SMTP_TEST_RECIPIENT") or from_email

    missing = [k for k in ["SMTP_SERVER", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD", "FROM_EMAIL"] if not env.get(k)]
    if missing:
        print(f"Cannot test SMTP; missing keys: {', '.join(missing)}")
        return
    if smtp_port <= 0:
        print("Invalid SMTP_PORT; cannot test SMTP.")
        return

    if not prompt_yes_no(f"Test SMTP connection and send a test email to {to_email}?", default=True):
        return

    import smtplib
    from email.message import EmailMessage

    msg = EmailMessage()
    msg["Subject"] = "SMTP test - UserManagementWithEmailOtp"
    msg["From"] = from_email
    msg["To"] = to_email
    msg.set_content("SMTP connectivity test from launcher.py")

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=20) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
        print(f"SMTP test email sent to {to_email}")
    except Exception as exc:
        print(f"SMTP test failed: {exc}")


def start_api(python_path: str):
    """Prompt to start uvicorn with reload using the selected interpreter."""
    if prompt_yes_no("Start FastAPI server now?", default=True):
        print("Starting API server (Ctrl+C to stop)...")
        run(
            [
                python_path,
                "-m",
                "uvicorn",
                "app.main:app",
                "--reload",
                "--host",
                "0.0.0.0",
                "--port",
                "8000",
            ],
            check=False,
        )


def apply_simple_migrations(python_path: str, db_url: str | None):
    """Apply idempotent schema changes if the database is reachable.

    This keeps the user table aligned with current code (e.g., social login columns)
    without needing a full migration tool in this starter project.
    """

    if not db_url:
        print("Skipping migrations: DATABASE_URL not set.")
        return

    migration_script = f"""
import asyncio
import asyncpg

DB_URL = {db_url!r}
SQL = [
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(50) NOT NULL DEFAULT 'local';",
    "ALTER TABLE users ADD COLUMN IF NOT EXISTS provider_id VARCHAR(255);",
    "ALTER TABLE users ALTER COLUMN hashed_password DROP NOT NULL;"
]

async def main():
    conn = await asyncpg.connect(DB_URL)
    try:
        for stmt in SQL:
            await conn.execute(stmt)
        print("Migrations applied.")
    finally:
        await conn.close()

asyncio.run(main())
"""
    try:
        run([python_path, "-c", migration_script])
    except FileNotFoundError:
        print("Migration step skipped: asyncpg not available. Install dependencies first.")
    except Exception as exc:
        print(f"Migration step failed: {exc}")


def main():
    """Primary orchestrator for the launcher workflow."""
    uv_cmd = ensure_uv()
    target_python = ensure_python("3.12", uv_cmd)
    ensure_env_file()
    env = parse_env()
    report_env_gaps(env)

    venv_exists = ensure_venv(uv_cmd)
    if not venv_exists:
        if prompt_yes_no(f"Create .venv with Python at {target_python}?", default=True):
            create_venv(uv_cmd, target_python)
    elif not venv_python_matches("3.12"):
        if prompt_yes_no(".venv exists but is not Python 3.12. Recreate it?", default=True):
            recreate_venv(uv_cmd, target_python)
    install_dependencies(uv_cmd, str(venv_python()))

    if not docker_available():
        install_docker()

    pg_cfg = parse_database_settings(env)
    redis_cfg = parse_redis_settings(env)

    ensure_postgres_container(pg_cfg, env)
    ensure_redis_container(redis_cfg, env)
    apply_simple_migrations(str(venv_python()), env.get("DATABASE_URL"))
    test_smtp(env)

    start_api(str(venv_python()))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nShutting down.")
    except Exception as exc:
        print(f"Error: {exc}")
        sys.exit(1)
