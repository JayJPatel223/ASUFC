"""Run the staff application and its database on the same offline computer."""

import argparse
import asyncio
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
from contextlib import asynccontextmanager, contextmanager
from datetime import date
from tempfile import TemporaryFile

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
import psycopg
from pydantic import BaseModel, Field
from starlette.responses import StreamingResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles
import uvicorn

from .credentials import validate_password
from .desktop_backup import BLOCK, BackupError, LedgerNotEmpty, restore_empty_ledger, write_backup
from .main import app, db, initialize_schema, safe_validation_error, staff

DESKTOP_COOKIE = "asufc_desktop_session"


def announce(status, **details):
    print(json.dumps({"status": status, **details}), flush=True)


def load_database_password(state_dir, database_dir):
    password_file = state_dir / "database-password"
    if password_file.exists():
        password = password_file.read_text(encoding="ascii").strip()
        if len(password) != 64 or any(character not in "0123456789abcdef" for character in password):
            raise ValueError("The local database configuration is damaged")
        return password
    if database_dir.exists():
        raise ValueError("Restore the password file that belongs to the existing local database")
    password = secrets.token_hex(32)
    # The desktop installer places this directory inside the current user's app data.
    with os.fdopen(os.open(password_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as output:
        output.write(password + "\n")
    return password


def postgres_tool(bin_dir, name, *arguments):
    binary = bin_dir / (name + (".exe" if os.name == "nt" else ""))
    environment = os.environ.copy()
    if os.name == "nt":
        environment["PATH"] = str(bin_dir) + os.pathsep + environment.get("PATH", "")
    if sys.platform.startswith("linux") and getattr(sys, "frozen", False):
        original_path = environment.pop("LD_LIBRARY_PATH_ORIG", None)
        if original_path is None:
            environment.pop("LD_LIBRARY_PATH", None)
        else:
            environment["LD_LIBRARY_PATH"] = original_path
    try:
        subprocess.run(
            [str(binary), *map(str, arguments)],
            stdin=subprocess.DEVNULL,
            stdout=sys.stderr,
            stderr=sys.stderr,
            check=True,
            timeout=60,
            env=environment,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
    except (OSError, subprocess.SubprocessError) as error:
        detail = error.strerror if isinstance(error, OSError) else getattr(error, "returncode", "timeout")
        print(f"Local database command {name} failed ({type(error).__name__}: {detail})", file=sys.stderr, flush=True)
        raise


def allocate_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@contextmanager
def local_database(state_dir, bin_dir):
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    database_dir = state_dir / "ledger"
    has_database = (database_dir / "PG_VERSION").is_file()
    password = load_database_password(state_dir, database_dir)
    if not has_database:
        if database_dir.exists() and any(database_dir.iterdir()):
            raise ValueError("The ledger directory is incomplete and needs recovery")
        postgres_tool(
            bin_dir, "initdb", "-D", database_dir, "-U", "asufc",
            "--auth=scram-sha-256", "--encoding=UTF8", "--locale=C",
            "--pwfile", state_dir / "database-password",
        )
    port = allocate_port()
    server_options = f"-h 127.0.0.1 -p {port} -c unix_socket_directories="
    postgres_tool(bin_dir, "pg_ctl", "-D", database_dir, "-l", state_dir / "postgres.log",
                  "-w", "-t", "30", "-o", server_options, "start")
    try:
        # Use the private cluster even if the desktop was started from a shell
        # whose PostgreSQL environment points elsewhere.
        settings = {
            "PGHOST": "127.0.0.1", "PGPORT": str(port), "PGUSER": "asufc",
            "PGPASSWORD": password, "PGDATABASE": "postgres", "PGSSLMODE": "disable",
        }
        for key in tuple(os.environ):
            if key.upper().startswith("PG"):
                del os.environ[key]
        os.environ.update(settings)
        yield
    finally:
        postgres_tool(bin_dir, "pg_ctl", "-D", database_dir, "-m", "fast", "-w", "-t", "25", "stop")


class BackupRequest(BaseModel):
    passphrase: str = Field(min_length=16, max_length=1024)


class RestoreRequest(BackupRequest):
    path: str = Field(min_length=1, max_length=32767)


def restore_local_backup(payload: RestoreRequest):
    # This path is supplied by the privileged desktop launcher after a native file picker.
    try:
        with Path(payload.path).open("rb") as file, db() as connection:
            restore_empty_ledger(connection, file, payload.passphrase)
    except LedgerNotEmpty as error:
        raise HTTPException(409, str(error)) from None
    except psycopg.errors.LockNotAvailable:
        raise HTTPException(409, "The ledger is busy. Try restoring again in a moment.") from None
    except BackupError as error:
        raise HTTPException(422, str(error)) from None
    except (OSError, ValueError, psycopg.Error):
        raise HTTPException(422, "The backup could not be restored. Check the file and try again.") from None
    return {"ok": True}


backup_lock = threading.Lock()
pending_backups = {}


def discard_backup(key):
    with backup_lock:
        entry = pending_backups.pop(key, None)
    if entry:
        entry[0].close()


def create_backup(payload: BackupRequest):
    try:
        validate_password(payload.passphrase)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if not backup_lock.acquire(blocking=False):
        raise HTTPException(409, "A backup is already being prepared. Try again in a moment.")
    try:
        if pending_backups:
            raise HTTPException(409, "A backup is already waiting to download.")
        archive = TemporaryFile()
        try:
            with db() as connection:
                write_backup(connection, archive, payload.passphrase)
            size = archive.tell()
            archive.seek(0)
        except (OSError, ValueError, psycopg.Error):
            archive.close()
            raise HTTPException(500, "Could not create a backup. Check free disk space and try again.") from None
        key = secrets.token_urlsafe(32)
        timer = threading.Timer(60, discard_backup, args=(key,))
        timer.daemon = True
        pending_backups[key] = archive, size, timer
        timer.start()
        return {"key": key}
    finally:
        backup_lock.release()


def download_backup(key: str):
    with backup_lock:
        entry = pending_backups.pop(key, None)
    if not entry:
        raise HTTPException(404, "This backup download expired. Create a new backup.")
    archive, size, timer = entry
    timer.cancel()

    def download():
        with archive:
            while data := archive.read(BLOCK):
                yield data

    return StreamingResponse(download(), media_type="application/octet-stream", headers={
        "Content-Disposition": f'attachment; filename="ASUFC-Finance-{date.today().isoformat()}.asufcbak"',
        "Content-Length": str(size),
        "Cache-Control": "no-store",
    })


def serve_staff(frontend_dir, launch_key):
    def authorize(request, supplied):
        if len(supplied) != len(launch_key) or not secrets.compare_digest(supplied.encode(), launch_key.encode()):
            raise HTTPException(401, "Open the ledger in ASUFC Finance.")
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("X-ASUFC-Request") != "1":
            raise HTTPException(403, "Missing request protection header")
        return "staff"

    def desktop_staff(request: Request):
        return authorize(request, request.cookies.get(DESKTOP_COOKIE, ""))

    def desktop_launcher(request: Request):
        return authorize(request, request.headers.get("X-ASUFC-Launcher", ""))

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

        @asynccontextmanager
        async def lifespan(_):
            with db() as connection:
                initialize_schema(connection)
            app.dependency_overrides[staff] = desktop_staff
            try:
                yield
            finally:
                del app.dependency_overrides[staff]

        desktop_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
        desktop_app.add_exception_handler(RequestValidationError, safe_validation_error)
        desktop_app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1"])
        desktop_app.add_api_route("/api/desktop/backup", create_backup, methods=["POST"], dependencies=[Depends(desktop_staff)])
        desktop_app.add_api_route("/api/desktop/backup/{key}", download_backup, methods=["GET"], dependencies=[Depends(desktop_staff)])
        desktop_app.add_api_route("/api/desktop/restore", restore_local_backup, methods=["POST"], dependencies=[Depends(desktop_launcher)])
        desktop_app.mount("/api", app)
        desktop_app.mount("/", StaticFiles(directory=frontend_dir, html=True))

        @desktop_app.middleware("http")
        async def security_headers(request, call_next):
            # The deployed staff web API keeps its password and session routes.
            if request.url.path.startswith("/api/auth/"):
                response = Response(status_code=404)
            else:
                response = await call_next(request)
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data:; connect-src 'self'; worker-src 'self'; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
            )
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Referrer-Policy"] = "no-referrer"
            return response

        class DesktopServer(uvicorn.Server):
            async def startup(self, sockets=None):
                await super().startup(sockets)
                if self.started:
                    announce("ready", port=port)

        server = DesktopServer(uvicorn.Config(
            desktop_app, http="h11", ws="none", loop="asyncio",
            log_config=None, access_log=False, proxy_headers=False, timeout_graceful_shutdown=15,
        ))

        def stop_when_launcher_exits():
            sys.stdin.read()
            server.should_exit = True

        threading.Thread(target=stop_when_launcher_exits, daemon=True).start()
        if os.name == "nt":
            # Windows' proactor transport can leave a reset HTTP connection
            # attached during shutdown. This small local server uses TCP only.
            asyncio.run(server.serve(sockets=[listener]), loop_factory=asyncio.SelectorEventLoop)
        else:
            server.run(sockets=[listener])
        if not server.started:
            raise RuntimeError("The staff application did not start")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", required=True, type=Path)
    parser.add_argument("--postgres-bin", required=True, type=Path)
    parser.add_argument("--frontend", required=True, type=Path)
    args = parser.parse_args()
    try:
        if not (args.frontend / "index.html").is_file():
            raise ValueError("The staff application files are missing")
        # The launcher sends the per-process credential over its private stdin pipe.
        launch_line = sys.stdin.readline(66)
        launch_key = launch_line.removesuffix("\n")
        if not launch_line.endswith("\n") or len(launch_key) != 64 or any(ch not in "0123456789abcdef" for ch in launch_key):
            raise ValueError("Start the local ledger from the ASUFC Finance desktop app.")
        os.environ["STAFF_USER"] = "staff"
        with local_database(args.state_dir.resolve(), args.postgres_bin.resolve()):
            serve_staff(args.frontend.resolve(), launch_key)
    except ValueError as error:
        announce("error", message=str(error))
        return 1
    except (OSError, subprocess.SubprocessError, psycopg.Error, RuntimeError):
        announce("error", message="The local ledger could not start. Check the application log or contact support.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
