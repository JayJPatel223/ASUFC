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


def check_windows_signature(file):
    environment = os.environ | {"ASUFC_SIGNATURE_PATH": str(file)}
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                    "if ((Get-AuthenticodeSignature -LiteralPath $env:ASUFC_SIGNATURE_PATH).Status -ne 'Valid') { exit 1 }"],
                   env=environment, check=True, timeout=60)


def install(artifact, scratch):
    signed = os.getenv("VERIFY_DESKTOP_SIGNATURE") == "1"
    if sys.platform == "win32":
        if signed:
            check_windows_signature(artifact)
        destination = scratch / "Installed App"
        # NSIS requires /D to be the final argument, with an unquoted path.
        subprocess.run(f'"{artifact}" /S /D={destination}', check=True, timeout=240)
        if signed:
            check_windows_signature(destination / "ASUFC Finance.exe")
        return destination / "resources" / "runtime"
    if sys.platform == "darwin":
        mount = scratch / "volume"
        destination = scratch / "ASUFC Finance.app"
        check("hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", mount, artifact)
        try:
            check("ditto", mount / "ASUFC Finance.app", destination)
        finally:
            check("hdiutil", "detach", mount)
        if signed:
            check("codesign", "--verify", "--deep", "--strict", destination)
            check("xcrun", "stapler", "validate", destination)
            check("spctl", "--assess", "--type", "execute", destination)
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
        if sys.platform == "win32":
            staged_bin = ROOT / "desktop" / "runtime" / "postgres" / "bin"
            installed_bin = runtime / "postgres" / "bin"
            missing = [file.name for file in staged_bin.iterdir() if file.is_file() and not (installed_bin / file.name).is_file()]
            assert not missing, f"PostgreSQL files missing from NSIS installation: {missing}"
            check(installed_bin / "initdb.exe", "--version")
        check(sys.executable, ROOT / "scripts" / "verify_desktop_runtime.py", "--", executable,
              "--frontend", runtime / "frontend", "--postgres-bin", runtime / "postgres" / "bin")
    with artifact.open("rb") as file:
        checksum = hashlib.file_digest(file, "sha256").hexdigest()
    (RELEASE / "SHA256SUMS.txt").write_text(f"{checksum}  {artifact.name}\n", encoding="ascii")
    print("Verified the runtime and recovery from the installed or extracted release artifact:", artifact.name)


if __name__ == "__main__":
    main()
