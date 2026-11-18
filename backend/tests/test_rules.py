from datetime import date, timedelta
import pytest
from app.rules import validate_purchase

def split(**kw):
    return dict(budget_id=1,cents=25000,remaining=50000,academic_year="2026-2027",expiry=None,eligible_program=None,eligible_supplier=None,program_code="ASUFCFSBP",funding_id=1,fund_remaining=50000)|kw

def check(rows,total=25000):
    validate_purchase(total,rows,date.today(),"Example supplier")

def test_valid(): check([split()])
def test_split(): check([split(cents=10000),split(budget_id=2,cents=15000)])
@pytest.mark.parametrize("row",[
    dict(cents=100),dict(remaining=100),dict(fund_remaining=100),
    dict(expiry=date.today()-timedelta(days=1)),dict(eligible_program="ASUFCGR"),
    dict(eligible_supplier="Other supplier")])
def test_invalid(row):
    with pytest.raises(ValueError): check([split(**row)])
def test_shared_fund():
    with pytest.raises(ValueError):
        check([split(cents=10000,fund_remaining=20000),split(budget_id=2,cents=15000,fund_remaining=20000)])
