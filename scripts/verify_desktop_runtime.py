"""Exercise the offline runtime with a disposable local ledger."""

import argparse
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
YEAR = "2026-2027"


@contextmanager
def launch(command, state, needs_setup):
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
                process.stdin.write(json.dumps({"password": PASSWORD}) + "\n")
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


def verify(base, record):
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

    try:
        fetch("/api/funding")
    except HTTPError as error:
        assert error.code == 401, error.code
    else:
        raise AssertionError("Funding records are accessible without signing in")

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
        api("/transactions", {
            "purchase_date": "2026-11-04", "supplier": "Example Shop", "purchase_type": "Food",
            "cents": 1250, "allocations": [{"budget_id": budget["id"], "cents": 1250}],
        })
    report = api("/reports/spending?year=" + YEAR)
    assert report["totals"] == {"cash_cents": 1250, "credit_cents": 0}
    assert report["purchase_count"] == 1
    funds = api("/funding")
    assert len(funds) == 1 and funds[0]["remaining_cents"] == 8750 and funds[0]["received_cents"] == 10000
    assert api("/reports/reconciliation?year=" + YEAR)["ok"]
    with fetch("/api/reports/spending.xlsx?year=" + YEAR) as response:
        with ZipFile(BytesIO(response.read())) as workbook:
            assert "xl/workbook.xml" in workbook.namelist()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Runtime command with frontend and PostgreSQL paths")
    args = parser.parse_args()
    command = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not command:
        parser.error("Provide the desktop runtime command after --")
    with TemporaryDirectory(prefix="asufc-desktop-") as path:
        state = Path(path)
        with launch(command, state, needs_setup=True) as base:
            verify(base, record=True)
        assert (state / "ledger" / "PG_VERSION").is_file()
        with launch(command, state, needs_setup=False) as base:
            verify(base, record=False)
    print("Verified local setup, sign-in, purchases, reports, export, and persistence after relaunch.")


if __name__ == "__main__":
    main()
