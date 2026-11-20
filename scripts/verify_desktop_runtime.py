"""Exercise the offline runtime with a disposable local ledger."""

import argparse
import base64
from contextlib import contextmanager
from http.cookiejar import CookieJar
from io import BytesIO
import json
from pathlib import Path
from queue import Queue
import re
import subprocess
from tempfile import TemporaryDirectory
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, ProxyHandler, Request, build_opener
from zipfile import ZipFile

PASSWORD = "fictional-offline-test-only"
BACKUP_PASSWORD = "fictional-backup-test-only"
YEAR = "2026-2027"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAMAAAACCAIAAAASFvFNAAAAFklEQVR4nGP8//8/AwMDAwMDEwMMAAA2BgMB1iHsRQAAAABJRU5ErkJggg==")
PDF = b"%PDF-1.4\n% Example receipt for testing\n%%EOF\n"


@contextmanager
def launch(command, state, needs_setup, restore=None):
    with subprocess.Popen(
        [*command, "--state-dir", str(state)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        text=True, encoding="utf-8",
    ) as process:
        events = Queue()

        def read_events():
            for line in process.stdout:
                events.put(json.loads(line))
            events.put({"status": "stopped"})

        threading.Thread(target=read_events, daemon=True).start()
        try:
            event = events.get(timeout=90)
            if needs_setup:
                assert event["status"] == "setup_required", event
                process.stdin.write(json.dumps({"password": "short"}) + "\n")
                process.stdin.flush()
                assert events.get(timeout=10)["status"] == "setup_error"
                if restore:
                    damaged = restore.with_suffix(".damaged")
                    damaged.write_bytes(restore.read_bytes()[:-1])
                    for file, password, message in [
                        (restore, "a long but wrong passphrase", "incorrect"),
                        (damaged, BACKUP_PASSWORD, "incomplete"),
                    ]:
                        process.stdin.write(json.dumps({"password": password, "restore_path": str(file)}) + "\n")
                        process.stdin.flush()
                        failure = events.get(timeout=45)
                        assert failure["status"] == "setup_error" and message in failure["message"], failure
                    payload = {"password": BACKUP_PASSWORD, "restore_path": str(restore)}
                else:
                    payload = {"password": PASSWORD}
                process.stdin.write(json.dumps(payload) + "\n")
                process.stdin.flush()
                event = events.get(timeout=45)
            assert event["status"] == "ready", event
            yield f"http://127.0.0.1:{event['port']}"
        finally:
            process.stdin.close()
            try:
                process.wait(timeout=45)
            except subprocess.TimeoutExpired:
                process.kill()
                raise
        assert process.returncode == 0, process.returncode


def verify(base, record, backup=None):
    client = build_opener(ProxyHandler({}), HTTPCookieProcessor(CookieJar()))

    def fetch(path, data=None):
        return client.open(Request(
            base + path,
            data=json.dumps(data).encode("utf-8") if data is not None else None,
            headers={"Content-Type": "application/json", "X-ASUFC-Request": "1"},
        ), timeout=5)

    for attempt in range(30):
        try:
            with fetch("/") as page:
                html = page.read().decode("utf-8")
                assert page.headers["Content-Security-Policy"]
            break
        except URLError:
            if attempt == 29:
                raise
            time.sleep(0.25)
    assets = re.findall(r'["\'](/assets/[^"\']+)["\']', html)
    assert any(asset.endswith(".js") for asset in assets)
    assert any(asset.endswith(".css") for asset in assets)
    for asset in assets:
        with fetch(asset) as response:
            assert response.status == 200 and response.read()

    def reject(path, code, data=None):
        try:
            with fetch(path, data):
                raise AssertionError(f"{path} did not return {code}")
        except HTTPError as error:
            assert error.code == code, (error.code, error.read())

    reject("/api/funding", 401)
    reject("/api/transactions/1/files/1", 401)
    reject("/api/desktop/backup", 401, {"passphrase": BACKUP_PASSWORD})

    def api(path, data=None):
        with fetch("/api" + path, data) as response:
            return json.load(response)

    assert api("/auth/login", {"username": "staff", "password": PASSWORD})["username"] == "staff"
    if record:
        source = api("/funding", {
            "name": "Fictional offline grant", "academic_year": YEAR, "kind": "cash",
            "expected_cents": 12000, "received_cents": 10000,
        })
        budget = api("/budgets", {"funding_id": source["id"], "program_code": "ASUFCGR", "cents": 5000})
        purchase = api("/transactions", {
            "purchase_date": "2026-11-04", "supplier": "Example Shop", "purchase_type": "Food",
            "cents": 1250, "allocations": [{"budget_id": budget["id"], "cents": 1250}],
        })
        path = f"/transactions/{purchase['id']}/files"
        initial = {"name": "Fictional receipt.png", "content": base64.b64encode(PNG).decode()}
        reject("/api" + path, 422, initial | {"name": "../receipt.png"})
        reject("/api" + path, 422, initial | {"content": "AAAA"})
        receipt = api(path, initial)
        reject("/api" + path, 409, initial)
        api(path, {"name": "Corrected fictional receipt.pdf", "content": base64.b64encode(PDF).decode(),
                   "replaces_id": receipt["id"], "reason": "Fictional replacement for the recovery test"})
        reject("/api" + path, 409, initial)
    report = api("/reports/spending?year=" + YEAR)
    assert report["totals"] == {"cash_cents": 1250, "credit_cents": 0}
    assert report["purchase_count"] == 1
    funds = api("/funding")
    assert len(funds) == 1 and funds[0]["remaining_cents"] == 8750 and funds[0]["received_cents"] == 10000
    assert api("/reports/reconciliation?year=" + YEAR)["ok"]
    purchase, = api("/transactions")
    path = f"/transactions/{purchase['id']}/files"
    current, original = api(path)
    assert current["replaces_id"] == original["id"] and original["replaced_by"] == current["id"]
    assert current["replacement_reason"] == "Fictional replacement for the recovery test"
    for row, content in [(current, PDF), (original, PNG)]:
        with fetch("/api" + path + "/" + str(row["id"])) as receipt:
            assert receipt.read() == content and receipt.headers["Content-Disposition"].startswith("attachment;")
    with fetch("/api/reports/spending.xlsx?year=" + YEAR) as response:
        with ZipFile(BytesIO(response.read())) as workbook:
            assert "xl/workbook.xml" in workbook.namelist()
    if backup:
        key = api("/desktop/backup", {"passphrase": BACKUP_PASSWORD})["key"]
        with fetch("/api/desktop/backup/" + key) as archive:
            data = archive.read()
        assert data.startswith(b"ASUFCBK")
        assert PDF not in data and b"Fictional offline grant" not in data
        backup.write_bytes(data)
        reject("/api/desktop/backup/" + key, 404)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Runtime command with frontend and PostgreSQL paths")
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        parser.error("Provide the desktop runtime command after --")
    with TemporaryDirectory(prefix="asufc-desktop-") as path:
        state = Path(path)
        backup = state / "fictional.asufcbak"
        with launch(command, state, needs_setup=True) as base:
            verify(base, record=True, backup=backup)
        assert (state / "ledger" / "PG_VERSION").is_file()
        with launch(command, state, needs_setup=False) as base:
            verify(base, record=False)
        with launch(command, state / "restored-copy", needs_setup=True, restore=backup) as base:
            verify(base, record=False)
    print("Verified local purchases, receipt history, reports, restart, and encrypted recovery into a fresh ledger.")


if __name__ == "__main__":
    main()
