"""Build a platform-specific staff runtime from the already built frontend."""

import argparse
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_VERSION = "16.16.0-beta.19"
POSTGRES_BUILDS = {
    ("linux", "x86_64"): "linux-x64",
    ("darwin", "arm64"): "darwin-arm64",
    ("darwin", "x86_64"): "darwin-x64",
    ("win32", "amd64"): "windows-x64",
}


def stage_postgres(directory):
    platform_key = sys.platform, platform.machine().lower()
    target = POSTGRES_BUILDS.get(platform_key)
    if not target:
        raise SystemExit(f"No desktop PostgreSQL build for {platform_key[0]} {platform_key[1]}")
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if not npm:
        raise SystemExit("npm is required to stage the PostgreSQL build")
    with TemporaryDirectory(prefix="asufc-postgres-build-") as temporary:
        result = subprocess.check_output([
            npm, "pack", "--json", "--pack-destination", temporary,
            f"@embedded-postgres/{target}@{POSTGRES_VERSION}",
        ], text=True)
        archive = Path(temporary) / json.loads(result)[0]["filename"]
        with tarfile.open(archive) as package:
            package.extractall(temporary, filter="data")
        extracted = Path(temporary) / "package"
        subprocess.run(["node", str(extracted / "scripts" / "hydrate-symlinks.js")], check=True)
        shutil.copytree(extracted / "native", directory, symlinks=True)
        shutil.copy2(extracted / "LICENSE.md", directory / "LICENSE.md")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory for the desktop runtime")
    args = parser.parse_args()
    output = args.output.resolve()
    frontend = ROOT / "frontend" / "dist"
    if not (frontend / "index.html").is_file():
        parser.error("Build the staff frontend with npm run build first")
    if output.exists():
        parser.error("Choose a new staging directory")
    output.mkdir(parents=True)
    shutil.copytree(frontend, output / "frontend")
    stage_postgres(output / "postgres")
    with TemporaryDirectory(prefix="asufc-pyinstaller-") as temporary:
        subprocess.run([
            sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--name", "asufc-backend", "--paths", "backend",
            "--workpath", temporary, "--specpath", temporary, "--distpath", str(output),
            "--add-data", "backend/app/schema.sql:app", "--collect-all", "psycopg_binary",
            "--hidden-import", "uvicorn.loops.asyncio", "--hidden-import", "uvicorn.protocols.http.h11_impl",
            "--hidden-import", "uvicorn.lifespan.on", "scripts/desktop_backend.py",
        ], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
