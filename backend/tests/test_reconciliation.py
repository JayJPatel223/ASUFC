from app.reconciliation import reconcile

def data():
    return ([dict(id=1,name="Grant",kind="cash",academic_year="2026-2027",received_cents=100000,expected_cents=120000),dict(id=2,name="Grant",kind="cash",academic_year="2027-2028",received_cents=0,expected_cents=0)],
    [dict(id=1,funding_id=1,program_code="ASUFCGR",cents=60000)],
    [dict(id=1,cents=25000,voided=False),dict(id=2,cents=10000,voided=True)],
    [dict(purchase_id=1,budget_id=1,cents=25000),dict(purchase_id=2,budget_id=1,cents=10000)],
    [dict(funding_id=1,cents=100000)],
    [dict(id=1,source_id=1,destination_id=2,cents=30000)])

def test_conserved_balances_and_voids():
    r=reconcile(*data(),"2026-2027")
    assert r["ok"]
    assert r["funding"][0]["remaining_cents"]==45000
    assert r["funding"][0]["unallocated_cents"]==10000
    assert r["budgets"][0]["spent_cents"]==25000
    dest=reconcile(*data(),"2027-2028")["funding"][0]
    assert dest["received_cents"]==0 and dest["capacity_cents"]==30000

def test_detect_inconsistent_records():
    f,b,p,a,r,t=data()
    r[0]["cents"]=90000
    b[0]["cents"]=10000
    p[0]["cents"]=30000
    result=reconcile(f,b,p,a,r,t,"2026-2027")
    assert not result["ok"]
    assert {"receipt_mismatch","purchase_allocation_mismatch","budget_overspent"} <= {i["code"] for i in result["issues"]}

def test_empty():
    assert reconcile([],[],[],[],[],[],"2026-2027")["ok"]
