from datetime import date
import pytest
from app.reporting import summarize, validate_period

def row(**kw):
    return dict(purchase_id=1, purchase_date=date(2026,11,11), program_code="ASUFCGR", supplier="Example", funding_id=1, funding_name="Grant", kind="cash", cents=15000) | kw

def test_splits_not_double_counted():
    r=summarize([row(),row(funding_id=2,kind="credit",cents=10000)])
    assert r["purchase_count"]==1
    assert r["totals"]=={"cash_cents":15000,"credit_cents":10000}
    assert r["program"]==[{"label":"ASUFCGR","cash_cents":15000,"credit_cents":10000}]

def test_months_and_suppliers():
    r=summarize([row(),row(purchase_id=2,purchase_date=date(2026,12,1),supplier="Other")])
    assert r["purchase_count"]==2
    assert [x["label"] for x in r["month"]]==["2026-11","2026-12"]
    assert len(r["supplier"])==2

def test_empty():
    assert summarize([])["totals"]=={"cash_cents":0,"credit_cents":0}

def test_invalid_period():
    with pytest.raises(ValueError):
        validate_period(date(2026,12,1),date(2026,11,1))
