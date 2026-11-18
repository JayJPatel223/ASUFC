"""Destructive tests against an explicitly designated disposable database."""
import os
from datetime import date
import pytest

pytestmark = pytest.mark.skipif(os.getenv("ASUFC_TEST_DATABASE") != "1", reason="Requires disposable PostgreSQL database")
@pytest.fixture
def client():
    from app.main import app, db
    from fastapi.testclient import TestClient
    assert os.environ["PGDATABASE"] == "asufc_test"
    with TestClient(app) as client:
        with db() as conn:
            conn.execute("TRUNCATE allocation,purchase,budget,funding RESTART IDENTITY CASCADE")
        client.auth=(os.environ["STAFF_USER"],os.environ["STAFF_PASSWORD"])
        yield client

def create(client,path,data):
    r=client.post(path,json=data)
    assert r.status_code==201,r.text
    return r.json()

def test_financial_workflow(client):
    f=create(client,"/funding",dict(name="Fictional test grant",academic_year="2026-2027",kind="cash",expected_cents=100000,received_cents=60000))
    g=create(client,"/funding",dict(name="Fictional credit",academic_year="2026-2027",kind="credit",expected_cents=300000,received_cents=300000))
    b=create(client,"/budgets",dict(funding_id=f["id"],program_code="ASUFCFSBP",cents=50000))
    c=create(client,"/budgets",dict(funding_id=g["id"],program_code="ASUFCFSBP",cents=100000))
    payload=dict(purchase_date=date.today().isoformat(),supplier="Test supplier",purchase_type="Groceries",cents=25000,allocations=[dict(budget_id=b["id"],cents=15000),dict(budget_id=c["id"],cents=10000)])
    tx=create(client,"/transactions",payload)
    assert tx["cents"]==25000
    data=client.get("/dashboard").json()
    totals={r["kind"]:r for r in data["funding"]}
    assert totals["cash"]["received"]==60000
    assert totals["cash"]["expected"]==40000
    assert totals["cash"]["spent"]==15000
    assert totals["credit"]["spent"]==10000
    assert data["programs"][0]["spent"]==25000
    assert len(client.get("/transactions").json())==1
    payload["allocations"][0]["cents"]=1
    assert client.post("/transactions",json=payload).status_code==422
    assert len(client.get("/transactions").json())==1
    assert client.get("/funding",auth=("wrong","wrong")).status_code==401
