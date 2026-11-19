from datetime import date
from io import BytesIO
from openpyxl import load_workbook
from app.export import spending_workbook

def test_workbook_split_and_text_safety():
    base=dict(purchase_id=1,purchase_date=date(2026,11,11),program_code="ASUFCGR",supplier="=1+1",funding_id=1,funding_name="Grant",kind="cash",cents=15000)
    rows=[base,base|dict(funding_id=2,kind="credit",cents=10000)]
    wb=load_workbook(BytesIO(spending_workbook(rows,{"Academic year":"2026-2027"})))
    assert wb.sheetnames==["Summary","Month","Program","Supplier","Funding","Allocations"]
    assert wb["Allocations"]["D2"].data_type=="s"
    assert wb["Allocations"]["D2"].value=="=1+1"
    assert sum(wb["Allocations"].cell(i,10).value for i in (2,3))==250
    assert list(wb["Program"].values)[1]==("ASUFCGR",150,100)
    assert ("Distinct purchases",1) in list(wb["Summary"].values)

def test_empty_export():
    wb=load_workbook(BytesIO(spending_workbook([],{})))
    assert wb["Allocations"].max_row==1
    assert ("Cash spent",0) in list(wb["Summary"].values)

def test_reconciliation_export():
    from app.export import reconciliation_workbook
    report=dict(year="2026-2027",ok=False,issues=[dict(code="receipt_mismatch",record_id=1,expected=10000,actual=9000)],funding=[dict(id=1,name="=1+1",kind="cash",expected_cents=0,received_cents=10000,carried_in_cents=0,carried_out_cents=1000,capacity_cents=9000,allocated_cents=5000,spent_cents=2000,remaining_cents=7000,unallocated_cents=4000)],budgets=[])
    wb=load_workbook(BytesIO(reconciliation_workbook(report)))
    assert wb.sheetnames==["Reconciliation","Funding","Budgets","Issues"]
    assert wb["Funding"]["B2"].data_type=="s"
    assert wb["Funding"]["K2"].value==70
    assert wb["Issues"]["A2"].value=="receipt_mismatch"
