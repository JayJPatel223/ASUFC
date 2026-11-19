import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from fastapi.encoders import jsonable_encoder
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from .rules import validate_purchase
from .suggestions import suggest_allocations

def db():
    return psycopg.connect(row_factory=dict_row)

@asynccontextmanager
async def lifespan(app):
    if len(os.environ.get("STAFF_PASSWORD", "")) < 12 or os.environ["STAFF_PASSWORD"] == "replace-with-random-password":
        raise RuntimeError("Set a random staff password of at least 12 characters")
    with db() as conn:
        conn.execute(Path(__file__).with_name("schema.sql").read_text())
    yield

security = HTTPBasic()
def staff(c: HTTPBasicCredentials = Depends(security)):
    user_ok = secrets.compare_digest(c.username.encode(), os.environ.get("STAFF_USER","staff").encode())
    pass_ok = secrets.compare_digest(c.password.encode(), os.environ["STAFF_PASSWORD"].encode())
    if not (user_ok and pass_ok):
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate":"Basic"})

app = FastAPI(title="ASUFC development API", lifespan=lifespan, dependencies=[Depends(staff)])

class Funding(BaseModel):
    name: str = Field(min_length=1,max_length=200)
    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    kind: Literal["cash","credit"]
    expected_cents: int = Field(ge=0,le=10**12)
    received_cents: int = Field(ge=0,le=10**12)
    expiry: date | None = None
    eligible_program: str | None = None
    eligible_supplier: str | None = None
    organization: str = Field(default="",max_length=200)
    source_type: str = Field(default="",max_length=100)
    recurring: bool = False
    carry_eligible: bool = False
    expected_date: date | None = None
    notes: str = Field(default="",max_length=2000)
    received_on: date | None = None

class Receipt(BaseModel):
    received_cents: int = Field(ge=0,le=10**12)
    received_on: date | None = None

class Budget(BaseModel):
    funding_id: int
    program_code: str
    cents: int = Field(gt=0,le=10**12)

class Split(BaseModel):
    budget_id: int
    cents: int = Field(gt=0,le=10**12)

class Purchase(BaseModel):
    purchase_date: date
    supplier: str = Field(min_length=1,max_length=200)
    purchase_type: str = Field(min_length=1,max_length=100)
    description: str = Field(default="",max_length=1000)
    cents: int = Field(gt=0,le=10**12)
    allocations: list[Split] = Field(min_length=1,max_length=100)

def audit(c, action, entity, entity_id, details):
    c.execute('INSERT INTO audit_event(actor,action,entity,entity_id,details) VALUES (%s,%s,%s,%s,%s)',(os.environ.get('STAFF_USER','staff'),action,entity,entity_id,Jsonb(jsonable_encoder(details))))


def add_receipt(c,funding_id,cents,received_on):
    if received_on and received_on>date.today(): bad("Receipt date cannot be in the future")
    c.execute("INSERT INTO funding_receipt(funding_id,cents,received_on,actor) VALUES (%s,%s,%s,%s)",(funding_id,cents,received_on,os.environ.get("STAFF_USER","staff")))


def bad(message):
    raise HTTPException(422, message)

@app.get("/programs")
def programs():
    with db() as c:
        return c.execute("SELECT * FROM program ORDER BY code").fetchall()

@app.post("/funding", status_code=201)
def add_funding(f: Funding):
    if f.received_cents > f.expected_cents: bad("Received exceeds award")
    with db() as c:
        validate_year_label(f.academic_year)
        if f.eligible_program and not c.execute("SELECT 1 FROM program WHERE code=%s",(f.eligible_program,)).fetchone(): bad("Unknown program")
        created=c.execute("""INSERT INTO funding(name,academic_year,kind,expected_cents,received_cents,expiry,eligible_program,eligible_supplier,organization,source_type,recurring,expected_date,notes,carry_eligible)
         VALUES (%(name)s,%(academic_year)s,%(kind)s,%(expected_cents)s,%(received_cents)s,%(expiry)s,%(eligible_program)s,%(eligible_supplier)s,%(organization)s,%(source_type)s,%(recurring)s,%(expected_date)s,%(notes)s,%(carry_eligible)s) RETURNING *""",f.model_dump()).fetchone()
        if f.received_cents:
            add_receipt(c,created["id"],f.received_cents,f.received_on)
        audit(c,"created","funding",created["id"],created)
        return created

@app.patch("/funding/{funding_id}/received")
def confirm_funding(funding_id: int, r: Receipt):
    with db() as c:
        f=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(funding_id,)).fetchone()
        if not f: bad("Unknown funding")
        if not f["received_cents"] <= r.received_cents <= f["expected_cents"]: bad("Receipt must increase confirmed funding within award")
        updated=c.execute("UPDATE funding SET received_cents=%s WHERE id=%s RETURNING *",(r.received_cents,funding_id)).fetchone()
        if r.received_cents>f["received_cents"]:
            add_receipt(c,funding_id,r.received_cents-f["received_cents"],r.received_on)
        audit(c,"receipt_confirmed","funding",funding_id,{"before":f["received_cents"],"after":updated["received_cents"]})
        return updated

@app.get("/funding")
def funding():
    with db() as c:
        return c.execute("""SELECT f.*, capacity_cents-COALESCE((SELECT sum(a.cents) FROM active_allocation a JOIN budget b ON b.id=a.budget_id WHERE b.funding_id=f.id),0) AS remaining_cents,
        capacity_cents-COALESCE((SELECT sum(b.cents) FROM budget b WHERE b.funding_id=f.id),0) AS unallocated_cents FROM funding_capacity f ORDER BY id""").fetchall()

@app.post("/budgets",status_code=201)
def add_budget(b: Budget):
    with db() as c:
        f=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(b.funding_id,)).fetchone()
        if not f: bad("Unknown funding")
        if not c.execute("SELECT 1 FROM program WHERE code=%s",(b.program_code,)).fetchone(): bad("Unknown program")
        if f["eligible_program"] and f["eligible_program"] != b.program_code: bad("Program not eligible")
        if f["expiry"] and f["expiry"] < date.today(): bad("Funding expired")
        used=c.execute("SELECT COALESCE(sum(cents),0) AS n FROM budget WHERE funding_id=%s",(b.funding_id,)).fetchone()["n"]
        if used+b.cents>capacity(c,f["id"]): bad("Insufficient unallocated confirmed funding")
        if c.execute("SELECT 1 FROM budget WHERE funding_id=%s AND program_code=%s",(b.funding_id,b.program_code)).fetchone(): bad("Budget already exists")
        created=c.execute("INSERT INTO budget(funding_id,program_code,cents) VALUES (%(funding_id)s,%(program_code)s,%(cents)s) RETURNING *",b.model_dump()).fetchone()
        audit(c,"created","budget",created["id"],created)
        return created

BUDGET_QUERY="""SELECT b.*, f.name AS funding_name,f.kind,f.academic_year,f.expiry,f.eligible_program,f.eligible_supplier,
 b.cents-COALESCE((SELECT sum(a.cents) FROM active_allocation a WHERE a.budget_id=b.id),0) AS remaining,
 f.capacity_cents-COALESCE((SELECT sum(a.cents) FROM active_allocation a JOIN budget bb ON bb.id=a.budget_id WHERE bb.funding_id=f.id),0) AS fund_remaining
 FROM budget b JOIN funding_capacity f ON f.id=b.funding_id"""

@app.get("/budgets")
def budgets():
    with db() as c:
        return c.execute(BUDGET_QUERY+" ORDER BY b.id").fetchall()

@app.post("/transactions",status_code=201)
def record(p: Purchase):
    with db() as c:
        return save_purchase(c,p)


def save_purchase(c,p):
    ids=[a.budget_id for a in p.allocations]
    # Serialize writers by funding source, then read fresh balances.
    c.execute("SELECT id FROM funding WHERE id IN (SELECT funding_id FROM budget WHERE id=ANY(%s)) ORDER BY id FOR UPDATE",(ids,)).fetchall()
    rows={r["id"]:r for r in c.execute(BUDGET_QUERY+" WHERE b.id=ANY(%s)",(ids,)).fetchall()}
    if any(i not in rows for i in ids): bad("Unknown budget")
    splits=[{**rows[a.budget_id],**a.model_dump()} for a in p.allocations]
    for year in {a["academic_year"] for a in splits}:
        period=c.execute("SELECT * FROM academic_period WHERE academic_year=%s",(year,)).fetchone()
        if period and not period["starts_on"] <= p.purchase_date <= period["ends_on"]: bad("Purchase date outside configured academic year")
    try: validate_purchase(p.cents,splits,p.purchase_date,p.supplier)
    except ValueError as e: bad(str(e))
    tx=c.execute("INSERT INTO purchase(purchase_date,supplier,purchase_type,description,cents) VALUES (%(purchase_date)s,%(supplier)s,%(purchase_type)s,%(description)s,%(cents)s) RETURNING *",p.model_dump()).fetchone()
    for a in p.allocations:
        c.execute("INSERT INTO allocation VALUES (%s,%s,%s)",(tx["id"],a.budget_id,a.cents))
    audit(c,"created","purchase",tx["id"],p.model_dump())
    return tx

@app.get("/transactions")
def transactions():
    with db() as c:
        return c.execute("""SELECT p.*, CASE WHEN v.purchase_id IS NULL THEN 'confirmed' ELSE 'voided' END AS status, v.reason AS void_reason, v.created_at AS voided_at, (SELECT replacement_id FROM purchase_correction WHERE original_id=p.id) AS replacement_id, (SELECT original_id FROM purchase_correction WHERE replacement_id=p.id) AS original_id, (SELECT json_agg(json_build_object('budget_id',a.budget_id,'program',b.program_code,'funding',f.name,'kind',f.kind,'academic_year',f.academic_year,'cents',a.cents) ORDER BY a.budget_id)
        FROM allocation a JOIN budget b ON b.id=a.budget_id JOIN funding f ON f.id=b.funding_id WHERE a.purchase_id=p.id) AS allocations FROM purchase p LEFT JOIN purchase_void v ON v.purchase_id=p.id ORDER BY p.purchase_date DESC,p.id DESC""").fetchall()

@app.get("/dashboard")
def dashboard(year: str = "2026-2027"):
    with db() as c:
        return {"funding":c.execute("""SELECT kind, sum(received_cents) AS received, sum(expected_cents-received_cents) AS expected, sum(carried_in_cents) AS carried_in, sum(carried_out_cents) AS carried_out, sum(capacity_cents) AS capacity,
        sum(COALESCE((SELECT sum(a.cents) FROM active_allocation a JOIN budget b ON b.id=a.budget_id WHERE b.funding_id=f.id),0)) AS spent
        FROM funding_capacity f WHERE academic_year=%s GROUP BY kind""",(year,)).fetchall(),
        "programs":c.execute("""SELECT b.program_code, sum(b.cents) AS allocated,
        sum(COALESCE((SELECT sum(a.cents) FROM active_allocation a WHERE a.budget_id=b.id),0)) AS spent FROM budget b JOIN funding f ON f.id=b.funding_id WHERE f.academic_year=%s GROUP BY b.program_code""",(year,)).fetchall()}


class SuggestionRequest(BaseModel):
    program_code: str
    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    kind: Literal["cash","credit"]
    supplier: str = Field(min_length=1,max_length=200)
    purchase_date: date
    cents: int = Field(gt=0,le=10**12)
    preferred_funding: int | None = None

@app.post("/allocation-suggestions")
def allocate_suggestion(p: SuggestionRequest):
    with db() as c:
        rows=c.execute(BUDGET_QUERY+" WHERE b.program_code=%s AND f.academic_year=%s",(p.program_code,p.academic_year)).fetchall()
        try:
            return suggest_allocations(rows,p.cents,p.program_code,p.academic_year,p.kind,p.supplier,p.purchase_date,p.preferred_funding)
        except ValueError as e:
            bad(str(e))

class ChangeReason(BaseModel):
    reason: str = Field(min_length=1,max_length=1000)

class BudgetChange(ChangeReason):
    cents: int = Field(ge=0,le=10**12)

@app.post("/transactions/{purchase_id}/void")
def void_purchase(purchase_id: int, change: ChangeReason):
    if not change.reason.strip(): bad("Reason required")
    with db() as c:
        p=c.execute("SELECT * FROM purchase WHERE id=%s FOR UPDATE",(purchase_id,)).fetchone()
        if not p: raise HTTPException(404,"Unknown purchase")
        c.execute("SELECT id FROM funding WHERE id IN (SELECT b.funding_id FROM budget b JOIN allocation a ON a.budget_id=b.id WHERE a.purchase_id=%s) ORDER BY id FOR UPDATE",(purchase_id,)).fetchall()
        if c.execute("SELECT 1 FROM purchase_void WHERE purchase_id=%s",(purchase_id,)).fetchone():
            raise HTTPException(409,"Purchase already voided")
        result=c.execute("INSERT INTO purchase_void(purchase_id,reason,actor) VALUES (%s,%s,%s) RETURNING *",(purchase_id,change.reason.strip(),os.environ.get("STAFF_USER","staff"))).fetchone()
        audit(c,"voided","purchase",purchase_id,{"reason":change.reason.strip(),"original_cents":p["cents"]})
        return result

@app.patch("/budgets/{budget_id}")
def adjust_budget(budget_id: int, change: BudgetChange):
    if not change.reason.strip(): bad("Reason required")
    with db() as c:
        b=c.execute("SELECT * FROM budget WHERE id=%s",(budget_id,)).fetchone()
        if not b: raise HTTPException(404,"Unknown budget")
        f=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(b["funding_id"],)).fetchone()
        b=c.execute("SELECT * FROM budget WHERE id=%s FOR UPDATE",(budget_id,)).fetchone()
        spent=c.execute("SELECT COALESCE(sum(cents),0) AS n FROM active_allocation WHERE budget_id=%s",(budget_id,)).fetchone()["n"]
        other=c.execute("SELECT COALESCE(sum(cents),0) AS n FROM budget WHERE funding_id=%s AND id<>%s",(f["id"],budget_id)).fetchone()["n"]
        if change.cents < spent: bad("Budget cannot be less than confirmed spending")
        if change.cents+other > capacity(c,f["id"]): bad("Insufficient confirmed funding")
        if change.cents>b["cents"] and f["expiry"] and f["expiry"]<date.today(): bad("Funding expired")
        result=c.execute("UPDATE budget SET cents=%s WHERE id=%s RETURNING *",(change.cents,budget_id)).fetchone()
        audit(c,"adjusted","budget",budget_id,{"before":b["cents"],"after":change.cents,"reason":change.reason.strip()})
        return result

@app.get("/audit")
def audit_history():
    with db() as c:
        return c.execute("SELECT * FROM audit_event ORDER BY id DESC LIMIT 500").fetchall()

def report_rows(year: str = "2026-2027", start: date | None = None, end: date | None = None, program: str | None = None, supplier: str | None = None, funding_id: int | None = None, purchase_type: str | None = None):
    from .reporting import summarize, validate_period
    try:
        validate_period(start,end)
    except ValueError as e:
        bad(str(e))
    query = """SELECT p.id AS purchase_id,p.purchase_date,p.supplier,p.purchase_type,p.description,b.program_code,f.id AS funding_id,f.name AS funding_name,f.kind,a.cents
    FROM active_allocation a JOIN purchase p ON p.id=a.purchase_id JOIN budget b ON b.id=a.budget_id JOIN funding f ON f.id=b.funding_id WHERE f.academic_year=%s"""
    params = [year]
    for value, clause in [(start,"p.purchase_date >= %s"),(end,"p.purchase_date <= %s"),(program,"b.program_code = %s"),(supplier,"lower(p.supplier) = lower(%s)"),(funding_id,"f.id = %s"),(purchase_type,"lower(p.purchase_type) = lower(%s)")]:
        if value is not None:
            query += " AND " + clause
            params.append(value)
    with db() as c:
        return c.execute(query + " ORDER BY p.purchase_date,p.id,b.id",params).fetchall()

@app.get("/reports/spending")
def spending_report(year: str = "2026-2027", start: date | None = None, end: date | None = None, program: str | None = None, supplier: str | None = None, funding_id: int | None = None, purchase_type: str | None = None):
    from .reporting import summarize
    return summarize(report_rows(year,start,end,program,supplier,funding_id,purchase_type))

@app.get("/reports/spending.xlsx")
def spending_export(year: str = "2026-2027", start: date | None = None, end: date | None = None, program: str | None = None, supplier: str | None = None, funding_id: int | None = None, purchase_type: str | None = None):
    from fastapi.responses import Response
    from .export import spending_workbook
    rows=report_rows(year,start,end,program,supplier,funding_id,purchase_type)
    content=spending_workbook(rows,{"Academic year":year,"Start":start,"End":end,"Program":program,"Supplier":supplier,"Funding ID":funding_id,"Purchase type":purchase_type})
    return Response(content,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":'attachment; filename="asufc-spending.xlsx"',"Cache-Control":"no-store"})

class Correction(ChangeReason):
    replacement: Purchase

@app.post("/transactions/{purchase_id}/correct",status_code=201)
def correct_purchase(purchase_id: int, change: Correction):
    if not change.reason.strip(): bad("Reason required")
    with db() as c:
        original=c.execute("SELECT * FROM purchase WHERE id=%s FOR UPDATE",(purchase_id,)).fetchone()
        if not original: raise HTTPException(404,"Unknown purchase")
        if c.execute("SELECT 1 FROM purchase_void WHERE purchase_id=%s",(purchase_id,)).fetchone(): raise HTTPException(409,"Purchase already voided")
        ids=[a.budget_id for a in change.replacement.allocations]
        # Acquire old and new funding locks in one stable order.
        c.execute("SELECT id FROM funding WHERE id IN (SELECT funding_id FROM budget WHERE id=ANY(%s) OR id IN (SELECT budget_id FROM allocation WHERE purchase_id=%s)) ORDER BY id FOR UPDATE",(ids,purchase_id)).fetchall()
        old_year=c.execute("SELECT DISTINCT f.academic_year FROM allocation a JOIN budget b ON b.id=a.budget_id JOIN funding f ON f.id=b.funding_id WHERE a.purchase_id=%s",(purchase_id,)).fetchall()
        new_year=c.execute("SELECT DISTINCT f.academic_year FROM budget b JOIN funding f ON f.id=b.funding_id WHERE b.id=ANY(%s)",(ids,)).fetchall()
        if old_year!=new_year: bad("Correction must stay in original academic year")
        c.execute("INSERT INTO purchase_void(purchase_id,reason,actor) VALUES (%s,%s,%s)",(purchase_id,change.reason.strip(),os.environ.get("STAFF_USER","staff")))
        replacement=save_purchase(c,change.replacement)
        c.execute("INSERT INTO purchase_correction VALUES (%s,%s)",(purchase_id,replacement["id"]))
        audit(c,"corrected","purchase",purchase_id,{"replacement_id":replacement["id"],"reason":change.reason.strip()})
        return replacement

@app.get("/funding/{funding_id}/receipts")
def receipts(funding_id: int):
    with db() as c:
        if not c.execute("SELECT 1 FROM funding WHERE id=%s",(funding_id,)).fetchone(): raise HTTPException(404,"Unknown funding")
        return c.execute("SELECT * FROM funding_receipt WHERE funding_id=%s ORDER BY id",(funding_id,)).fetchall()

def validate_year_label(year):
    if len(year)!=9 or year[4]!="-" or not year[:4].isdigit() or not year[5:].isdigit() or int(year[5:])!=int(year[:4])+1:
        bad("Academic year must contain consecutive years, e.g. 2026-2027")

class AcademicPeriod(BaseModel):
    academic_year: str
    starts_on: date
    ends_on: date

class SemesterPeriod(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    starts_on: date
    ends_on: date

@app.get("/academic-years")
def academic_years():
    with db() as c:
        return c.execute("SELECT p.*, COALESCE((SELECT json_agg(s ORDER BY s.starts_on) FROM semester s WHERE s.period_id=p.id),'[]'::json) AS semesters FROM academic_period p ORDER BY starts_on").fetchall()

@app.post("/academic-years",status_code=201)
def create_academic_year(p: AcademicPeriod):
    validate_year_label(p.academic_year)
    if p.starts_on>p.ends_on or p.starts_on.year!=int(p.academic_year[:4]) or p.ends_on.year!=int(p.academic_year[5:]): bad("Dates must be ordered and match academic year")
    with db() as c:
        c.execute("LOCK TABLE funding IN EXCLUSIVE MODE")
        c.execute("LOCK TABLE academic_period IN SHARE ROW EXCLUSIVE MODE")
        if c.execute("SELECT 1 FROM academic_period WHERE starts_on<=%s AND ends_on>=%s",(p.ends_on,p.starts_on)).fetchone(): bad("Academic years cannot overlap")
        if c.execute("SELECT 1 FROM purchase p JOIN active_allocation a ON a.purchase_id=p.id JOIN budget b ON b.id=a.budget_id JOIN funding f ON f.id=b.funding_id WHERE f.academic_year=%s AND (p.purchase_date<%s OR p.purchase_date>%s)",(p.academic_year,p.starts_on,p.ends_on)).fetchone(): bad("Existing purchases fall outside these dates")
        row=c.execute("INSERT INTO academic_period(academic_year,starts_on,ends_on) VALUES (%(academic_year)s,%(starts_on)s,%(ends_on)s) RETURNING *",p.model_dump()).fetchone()
        audit(c,"created","academic_year",row["id"],row)
        return row

@app.post("/academic-years/{year}/semesters",status_code=201)
def create_semester(year: str,p: SemesterPeriod):
    with db() as c:
        period=c.execute("SELECT * FROM academic_period WHERE academic_year=%s FOR UPDATE",(year,)).fetchone()
        if not period: raise HTTPException(404,"Unknown academic year")
        if not p.name.strip() or not period["starts_on"]<=p.starts_on<=p.ends_on<=period["ends_on"]: bad("Semester dates must fit academic year")
        if c.execute("SELECT 1 FROM semester WHERE period_id=%s AND (name=%s OR (starts_on<=%s AND ends_on>=%s))",(period["id"],p.name.strip(),p.ends_on,p.starts_on)).fetchone(): bad("Duplicate or overlapping semester")
        row=c.execute("INSERT INTO semester(period_id,name,starts_on,ends_on) VALUES (%s,%s,%s,%s) RETURNING *",(period["id"],p.name.strip(),p.starts_on,p.ends_on)).fetchone()
        audit(c,"created","semester",row["id"],row)
        return row

def capacity(c,funding_id):
    return c.execute("SELECT capacity_cents FROM funding_capacity WHERE id=%s",(funding_id,)).fetchone()["capacity_cents"]

class CarryPermission(ChangeReason):
    eligible: bool

class CarryTransfer(ChangeReason):
    destination_year: str
    cents: int = Field(gt=0,le=10**12)

@app.patch("/funding/{funding_id}/carry-permission")
def carry_permission(funding_id: int,p: CarryPermission):
    if not p.reason.strip(): bad("Reason required")
    with db() as c:
        old=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(funding_id,)).fetchone()
        if not old: raise HTTPException(404,"Unknown funding")
        row=c.execute("UPDATE funding SET carry_eligible=%s WHERE id=%s RETURNING *",(p.eligible,funding_id)).fetchone()
        audit(c,"carry_permission_changed","funding",funding_id,{"before":old["carry_eligible"],"after":p.eligible,"reason":p.reason.strip()})
        return row

@app.post("/funding/{funding_id}/carry-forward",status_code=201)
def carry_forward(funding_id: int,p: CarryTransfer):
    if not p.reason.strip(): bad("Reason required")
    validate_year_label(p.destination_year)
    with db() as c:
        source=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(funding_id,)).fetchone()
        if not source: raise HTTPException(404,"Unknown funding")
        if not source["carry_eligible"]: bad("Grant carry-forward permission not confirmed")
        src=c.execute("SELECT * FROM academic_period WHERE academic_year=%s",(source["academic_year"],)).fetchone()
        dst=c.execute("SELECT * FROM academic_period WHERE academic_year=%s",(p.destination_year,)).fetchone()
        if not src or not dst: bad("Configure both academic years first")
        if int(p.destination_year[:4])!=int(source["academic_year"][:4])+1 or dst["starts_on"]<=src["ends_on"]: bad("Destination must be the next academic year")
        if source["expiry"] and source["expiry"]<max(dst["starts_on"],date.today()): bad("Funding expires before transfer can be used")
        reserved=c.execute("SELECT COALESCE(sum(cents),0) AS n FROM budget WHERE funding_id=%s",(funding_id,)).fetchone()["n"]
        if p.cents>capacity(c,funding_id)-reserved: bad("Release unused budget allocations before transferring")
        # A transfer creates a new funding bucket with no new award or receipt.
        dest=c.execute("""INSERT INTO funding(name,academic_year,kind,expected_cents,received_cents,expiry,eligible_program,eligible_supplier,organization,source_type,recurring,notes,carry_eligible)
        VALUES (%s,%s,%s,0,0,%s,%s,%s,%s,%s,false,%s,false) RETURNING *""",(source["name"],p.destination_year,source["kind"],source["expiry"],source["eligible_program"],source["eligible_supplier"],source["organization"],source["source_type"],source["notes"])).fetchone()
        transfer=c.execute("INSERT INTO funding_transfer(source_id,destination_id,cents,reason) VALUES (%s,%s,%s,%s) RETURNING *",(funding_id,dest["id"],p.cents,p.reason.strip())).fetchone()
        audit(c,"carried_forward","funding",funding_id,transfer)
        return transfer

@app.get("/funding-transfers")
def funding_transfers():
    with db() as c:
        return c.execute("SELECT t.*,s.academic_year AS source_year,d.academic_year AS destination_year,s.name AS funding_name,s.kind,v.transfer_id IS NOT NULL AS reversed,v.reason AS reversal_reason FROM funding_transfer t JOIN funding s ON s.id=t.source_id JOIN funding d ON d.id=t.destination_id LEFT JOIN funding_transfer_void v ON v.transfer_id=t.id ORDER BY t.id DESC").fetchall()

@app.get("/reports/reconciliation")
def reconciliation_report(year: str = "2026-2027"):
    from .reconciliation import reconcile
    validate_year_label(year)
    with db() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        funds=c.execute("SELECT * FROM funding ORDER BY id").fetchall()
        budgets=c.execute("SELECT * FROM budget ORDER BY id").fetchall()
        purchases=c.execute("SELECT p.*, v.purchase_id IS NOT NULL AS voided FROM purchase p LEFT JOIN purchase_void v ON v.purchase_id=p.id").fetchall()
        allocations=c.execute("SELECT * FROM allocation").fetchall()
        receipts=c.execute("SELECT * FROM funding_receipt").fetchall()
        transfers=c.execute("SELECT * FROM active_funding_transfer").fetchall()
        return reconcile(funds,budgets,purchases,allocations,receipts,transfers,year)

@app.get("/reports/reconciliation.xlsx")
def reconciliation_export(year: str = "2026-2027"):
    from fastapi.responses import Response
    from .export import reconciliation_workbook
    content=reconciliation_workbook(reconciliation_report(year))
    return Response(content,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":'attachment; filename="asufc-balances.xlsx"',"Cache-Control":"no-store"})

class ImportWorkbook(BaseModel):
    content_base64: str = Field(max_length=6700000)
    sheet: str = Field(min_length=1,max_length=100)
    mapping: dict[str,str]

def parse_import(p):
    from base64 import b64decode
    from .importing import parse_workbook
    try: return parse_workbook(b64decode(p.content_base64,validate=True),p.sheet,p.mapping)
    except (ValueError,TypeError) as e: bad(str(e))

def import_rows(c,parsed):
    if parsed["errors"]: bad("Resolve workbook validation errors first")
    if not parsed["rows"]: bad("No transactions to import")
    ids=[a["budget_id"] for r in parsed["rows"] for a in r["allocations"]]
    c.execute("SELECT id FROM funding WHERE id IN (SELECT funding_id FROM budget WHERE id=ANY(%s)) ORDER BY id FOR UPDATE",(ids,)).fetchall()
    result=[]
    for row in parsed["rows"]:
        ident=row["external_id"]
        if c.execute("SELECT 1 FROM import_entry WHERE external_id=%s",(ident,)).fetchone(): bad("Already imported external ID: "+ident)
        p=Purchase.model_validate({k:v for k,v in row.items() if k not in ("row","external_id")})
        # Exact date, supplier and amount matches are conservative review blockers.
        if c.execute("SELECT 1 FROM purchase p LEFT JOIN purchase_void v ON v.purchase_id=p.id WHERE v.purchase_id IS NULL AND p.purchase_date=%s AND lower(trim(p.supplier))=lower(trim(%s)) AND p.cents=%s",(p.purchase_date,p.supplier,p.cents)).fetchone(): bad("Possible duplicate purchase on row "+str(row["row"]))
        tx=save_purchase(c,p)
        inserted=c.execute("INSERT INTO import_entry(external_id,purchase_id) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING external_id",(ident,tx["id"])).fetchone()
        if not inserted: bad("Already imported external ID: "+ident)
        result.append(tx["id"])
    return result

@app.post("/imports/preview")
def preview_import(p: ImportWorkbook):
    parsed=parse_import(p)
    if parsed["errors"] or not parsed["rows"]: return parsed|{"valid":False}
    # Exercise the actual transaction path, then roll back everything.
    try:
        with db() as c:
            try: import_rows(c,parsed)
            finally: c.rollback()
    except HTTPException as e:
        return parsed|{"valid":False,"validation_error":e.detail}
    return parsed|{"valid":True}

@app.post("/imports/commit",status_code=201)
def commit_import(p: ImportWorkbook):
    parsed=parse_import(p)
    with db() as c:
        result=import_rows(c,parsed)
        audit(c,"imported","purchase",result[0],{"purchase_ids":result})
        return {"imported":len(result),"purchase_ids":result}

class NewProgram(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9&_-]{2,40}$")
    name: str = Field(min_length=1,max_length=200)

@app.post("/programs",status_code=201)
def create_program(p: NewProgram):
    if not p.name.strip(): bad("Name required")
    with db() as c:
        row=c.execute("INSERT INTO program(code,name) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING *",(p.code,p.name.strip())).fetchone()
        if not row: raise HTTPException(409,"Program code already exists")
        return row

@app.post("/funding-transfers/{transfer_id}/reverse")
def reverse_transfer(transfer_id: int,p: ChangeReason):
    if not p.reason.strip(): bad("Reason required")
    with db() as c:
        t=c.execute("SELECT * FROM funding_transfer WHERE id=%s FOR UPDATE",(transfer_id,)).fetchone()
        if not t: raise HTTPException(404,"Unknown transfer")
        c.execute("SELECT id FROM funding WHERE id=ANY(%s) ORDER BY id FOR UPDATE",([t["source_id"],t["destination_id"]],)).fetchall()
        if c.execute("SELECT 1 FROM funding_transfer_void WHERE transfer_id=%s",(transfer_id,)).fetchone(): raise HTTPException(409,"Transfer already reversed")
        reserved=c.execute("SELECT COALESCE(sum(cents),0) AS n FROM budget WHERE funding_id=%s",(t["destination_id"],)).fetchone()["n"]
        spent=c.execute("SELECT COALESCE(sum(a.cents),0) AS n FROM active_allocation a JOIN budget b ON b.id=a.budget_id WHERE b.funding_id=%s",(t["destination_id"],)).fetchone()["n"]
        if capacity(c,t["destination_id"])-t["cents"]<max(reserved,spent,0): bad("Destination funds are allocated, spent or transferred onward")
        row=c.execute("INSERT INTO funding_transfer_void(transfer_id,reason,actor) VALUES (%s,%s,%s) RETURNING *",(transfer_id,p.reason.strip(),os.environ.get("STAFF_USER","staff"))).fetchone()
        audit(c,"transfer_reversed","funding",t["source_id"],{"transfer_id":transfer_id,"reason":p.reason.strip()})
        return row
