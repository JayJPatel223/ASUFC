"""Install or unpack an actual release artifact and verify its bundled runtime."""

import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "desktop" / "release"


def check(*command, cwd=None):
    subprocess.run(list(map(str, command)), cwd=cwd, check=True, timeout=240)


def install(artifact, scratch):
    if sys.platform == "win32":
        destination = scratch / "Installed App"
        # NSIS requires /D to be the final argument, with an unquoted path.
        subprocess.run(f'"{artifact}" /S /D={destination}', check=True, timeout=240)
        return destination / "resources" / "runtime"
    if sys.platform == "darwin":
        mount = scratch / "volume"
        destination = scratch / "ASUFC Finance.app"
        check("hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", mount, artifact)
        try:
            check("ditto", mount / "ASUFC Finance.app", destination)
        finally:
            check("hdiutil", "detach", mount)
        return destination / "Contents" / "Resources" / "runtime"
    subprocess.run([artifact, "--appimage-extract"], cwd=scratch, check=True, timeout=240, stdout=subprocess.DEVNULL)
    return scratch / "squashfs-root" / "resources" / "runtime"


def main():
    extensions = {"win32": "exe", "darwin": "dmg", "linux": "AppImage"}
    artifact, = RELEASE.glob("ASUFC-Finance-*." + extensions[sys.platform])
    with TemporaryDirectory(prefix="asufc-installed-") as directory:
        runtime = install(artifact, Path(directory))
        executable = runtime / "asufc-backend" / ("asufc-backend.exe" if os.name == "nt" else "asufc-backend")
        assert executable.is_file(), f"Runtime was missing from the installed package: {executable}"
        check(sys.executable, ROOT / "scripts" / "verify_desktop_runtime.py", "--", executable,
              "--frontend", runtime / "frontend", "--postgres-bin", runtime / "postgres" / "bin")
    with artifact.open("rb") as file:
        checksum = hashlib.file_digest(file, "sha256").hexdigest()
    (RELEASE / "SHA256SUMS.txt").write_text(f"{checksum}  {artifact.name}\n", encoding="ascii")
    print("Verified the runtime and recovery from the installed or extracted release artifact:", artifact.name)


if __name__ == "__main__":
    main()
