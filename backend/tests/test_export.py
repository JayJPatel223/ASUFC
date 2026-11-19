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
