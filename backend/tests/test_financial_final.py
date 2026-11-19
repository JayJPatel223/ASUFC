from io import BytesIO
from openpyxl import Workbook
from app.importing import parse_workbook,FIELDS

def workbook(rows):
    w=Workbook();s=w.active;s.append(list(FIELDS))
    for row in rows:s.append(row)
    out=BytesIO();w.save(out)
    return parse_workbook(out.getvalue(),s.title,{k:k for k in FIELDS})

def test_split_import():
    r=workbook([["ID1","2026-11-01","Shop","Food","",100,1],["ID1","2026-11-01","Shop","Food","",150,2]])
    assert not r["errors"]
    assert len(r["rows"])==1
    assert r["rows"][0]["cents"]==25000
    assert len(r["rows"][0]["allocations"])==2

def test_split_duplicate_budget_rejected():
    r=workbook([["ID1","2026-11-01","Shop","Food","",100,1],["ID1","2026-11-01","Shop","Food","",150,1]])
    assert r["errors"]

def test_split_conflicting_metadata_rejected():
    r=workbook([["ID1","2026-11-01","Shop","Food","",100,1],["ID1","2026-11-02","Shop","Food","",150,2]])
    assert r["errors"]
