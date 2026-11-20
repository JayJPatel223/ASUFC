import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Annotated, Literal
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from fastapi.encoders import jsonable_encoder
from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from hashlib import sha256
from .credentials import hash_password,verify_password,validate_password
from pydantic import BaseModel, Field
from .rules import restriction_allows, spending_restriction, validate_purchase
from .suggestions import suggest_allocations
from .receipt_files import register_receipts

def db():
    return psycopg.connect(row_factory=dict_row)

@asynccontextmanager
async def lifespan(app):
    with db() as conn:
        conn.execute(Path(__file__).with_name("schema.sql").read_text())
        conn.execute("SELECT pg_advisory_xact_lock(2663002)")
        user=os.environ.get("STAFF_USER","staff")
        if not conn.execute("SELECT 1 FROM staff_credential WHERE username=%s",(user,)).fetchone():
            password=os.environ.get("STAFF_PASSWORD","")
            validate_password(password)
            conn.execute("INSERT INTO staff_credential(username,password_hash) VALUES (%s,%s)",(user,hash_password(password)))
    yield

COOKIE="asufc_session"
def token_hash(token):
    return sha256(token.encode()).hexdigest()

def staff(request: Request):
    token=request.cookies.get(COOKIE,"")
    if not token or len(token)>128: raise HTTPException(401,"Staff session required")
    if request.method not in ("GET","HEAD","OPTIONS") and request.headers.get("X-ASUFC-Request")!="1":
        raise HTTPException(403,"Missing request protection header")
    with db() as c:
        row=c.execute("SELECT username FROM staff_session WHERE token_hash=%s AND expires_at>now()",(token_hash(token),)).fetchone()
    if not row or row["username"]!=os.environ.get("STAFF_USER","staff"): raise HTTPException(401,"Staff session expired")
    return row["username"]

app = FastAPI(title="ASUFC development API", lifespan=lifespan,docs_url=None,redoc_url=None,openapi_url=None)
router=APIRouter(dependencies=[Depends(staff)])

@app.exception_handler(RequestValidationError)
async def safe_validation_error(request: Request, exc: RequestValidationError):
    # Validation errors must not echo credentials, uploaded data or arbitrary input.
    return JSONResponse(status_code=422,content={"detail":"Invalid request fields or values"},headers={"Cache-Control":"no-store"})

class Login(BaseModel):
    username: str = Field(max_length=200)
    password: str = Field(max_length=1024)

@app.post("/auth/login")
def login(p: Login,request: Request,response: Response):
    if request.headers.get("X-ASUFC-Request")!="1": raise HTTPException(403,"Missing request protection header")
    user=os.environ.get("STAFF_USER","staff")
    # Global account throttle suits a single designated staff account.
    with db() as c:
        c.execute("SELECT pg_advisory_xact_lock(2663002)")
        c.execute("DELETE FROM staff_login_attempt WHERE attempted_at<now()-interval '15 minutes'")
        attempts=c.execute("SELECT count(*) AS n FROM staff_login_attempt").fetchone()["n"]
        if attempts>=10: raise HTTPException(429,"Too many attempts; try again in 15 minutes")
        credential=c.execute("SELECT password_hash FROM staff_credential WHERE username=%s",(user,)).fetchone()
        valid=secrets.compare_digest(p.username.encode(),user.encode()) & verify_password(p.password,credential["password_hash"])
        if not valid:
            c.execute("INSERT INTO staff_login_attempt DEFAULT VALUES")
        else:
            c.execute("DELETE FROM staff_login_attempt")
            c.execute("DELETE FROM staff_session WHERE expires_at<=now()")
            previous=request.cookies.get(COOKIE,"")
            if previous and len(previous)<=128: c.execute("DELETE FROM staff_session WHERE token_hash=%s",(token_hash(previous),))
            token=secrets.token_urlsafe(32)
            c.execute("INSERT INTO staff_session(token_hash,username,expires_at) VALUES (%s,%s,now()+interval '8 hours')",(token_hash(token),user))
    if not valid: raise HTTPException(401,"Invalid staff credentials")
    response.set_cookie(COOKIE,token,max_age=28800,httponly=True,secure=os.getenv("SESSION_SECURE","1")!="0",samesite="strict",path="/")
    response.headers["Cache-Control"]="no-store"
    return {"username":user}

@router.get("/auth/session")
def session(username: str = Depends(staff)):
    return {"username":username}

@router.post("/auth/logout")
def logout(request: Request,response: Response):
    with db() as c: c.execute("DELETE FROM staff_session WHERE token_hash=%s",(token_hash(request.cookies[COOKIE]),))
    response.delete_cookie(COOKIE,path="/",secure=os.getenv("SESSION_SECURE","1")!="0",httponly=True,samesite="strict")
    return {"ok":True}

@app.middleware("http")
async def no_cache(request,call_next):
    response=await call_next(request)
    response.headers["Cache-Control"]="no-store"
    response.headers["X-Content-Type-Options"]="nosniff"
    return response

ProgramCode = Annotated[str, Field(min_length=1, max_length=40)]
SupplierName = Annotated[str, Field(min_length=1, max_length=200)]
PurchaseType = Annotated[str, Field(min_length=1, max_length=100)]

class Funding(BaseModel):
    name: str = Field(min_length=1,max_length=200)
    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    kind: Literal["cash","credit"]
    expected_cents: int = Field(ge=0,le=10**12)
    received_cents: int = Field(ge=0,le=10**12)
    expiry: date | None = None
    eligible_program: str | None = None
    eligible_supplier: str | None = None
    eligible_programs: list[ProgramCode] | None = Field(default=None, max_length=100)
    eligible_suppliers: list[SupplierName] | None = Field(default=None, max_length=100)
    eligible_purchase_types: list[PurchaseType] | None = Field(default=None, max_length=100)
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
    duplicate_reason: str = Field(default="",max_length=1000)

def audit(c, action, entity, entity_id, details):
    c.execute('INSERT INTO audit_event(actor,action,entity,entity_id,details) VALUES (%s,%s,%s,%s,%s)',(os.environ.get('STAFF_USER','staff'),action,entity,entity_id,Jsonb(jsonable_encoder(details))))


def add_receipt(c,funding_id,cents,received_on):
    if received_on and received_on>date.today(): bad("Receipt date cannot be in the future")
    c.execute("INSERT INTO funding_receipt(funding_id,cents,received_on,actor) VALUES (%s,%s,%s,%s)",(funding_id,cents,received_on,os.environ.get("STAFF_USER","staff")))


def bad(message):
    raise HTTPException(422, message)

ELIGIBILITY_FIELDS = ("eligible_programs", "eligible_suppliers", "eligible_purchase_types")

def normalize_eligibility(programs: list[str], suppliers: list[str], purchase_types: list[str]):
    rules = {}
    for field, values in zip(ELIGIBILITY_FIELDS, (programs, suppliers, purchase_types), strict=True):
        unique = {}
        for value in values:
            label = value.strip()
            if not label:
                bad("Spending rules cannot contain blank values")
            if "\x00" in label or len(label.splitlines()) != 1:
                bad("Enter one value per spending rule")
            key = label if field == "eligible_programs" else label.casefold()
            unique.setdefault(key, label)
        rules[field] = list(unique.values())
    return rules

def verify_eligible_programs(c, codes: list[str]):
    if codes and c.execute(
        "SELECT count(*) AS count FROM program WHERE code=ANY(%s)", (codes,)
    ).fetchone()["count"] != len(codes):
        bad("Unknown program in spending rules")

def funding_eligibility(c, funding_id: int):
    return c.execute(
        """SELECT eligible_programs, eligible_suppliers, eligible_purchase_types
           FROM effective_funding_eligibility WHERE funding_id=%s""", (funding_id,)
    ).fetchone()

def store_funding_eligibility(c, funding_id: int, rules: dict):
    c.execute("""INSERT INTO funding_eligibility
        (funding_id, eligible_programs, eligible_suppliers, eligible_purchase_types)
        VALUES (%(funding_id)s, %(eligible_programs)s, %(eligible_suppliers)s, %(eligible_purchase_types)s)
        ON CONFLICT (funding_id) DO UPDATE SET eligible_programs=excluded.eligible_programs,
        eligible_suppliers=excluded.eligible_suppliers, eligible_purchase_types=excluded.eligible_purchase_types
        """, {"funding_id": funding_id, **rules})

def funding_rule_fields(row: dict):
    result = row.copy()
    for field in ELIGIBILITY_FIELDS:
        values = result[field]
        result[field.removesuffix("s")] = values[0] if len(values) == 1 else None
    return result

@router.get("/programs")
def programs():
    with db() as c:
        return c.execute("SELECT * FROM program ORDER BY code").fetchall()

@router.post("/funding", status_code=201)
def add_funding(f: Funding):
    if f.received_cents > f.expected_cents: bad("Received exceeds award")
    has_new_rules = any(getattr(f, field) is not None for field in ELIGIBILITY_FIELDS)
    if ((f.eligible_program and f.eligible_programs is not None)
        or (f.eligible_supplier and f.eligible_suppliers is not None)):
        bad("Use one form of each spending rule")
    with db() as c:
        validate_year_label(f.academic_year)
        if f.eligible_program and not c.execute("SELECT 1 FROM program WHERE code=%s",(f.eligible_program,)).fetchone(): bad("Unknown program")
        if has_new_rules:
            rules = normalize_eligibility(
                f.eligible_programs if f.eligible_programs is not None else ([f.eligible_program] if f.eligible_program else []),
                f.eligible_suppliers if f.eligible_suppliers is not None else ([f.eligible_supplier] if f.eligible_supplier else []),
                f.eligible_purchase_types or [],
            )
            verify_eligible_programs(c, rules["eligible_programs"])
        created=c.execute("""INSERT INTO funding(name,academic_year,kind,expected_cents,received_cents,expiry,eligible_program,eligible_supplier,organization,source_type,recurring,expected_date,notes,carry_eligible)
         VALUES (%(name)s,%(academic_year)s,%(kind)s,%(expected_cents)s,%(received_cents)s,%(expiry)s,%(eligible_program)s,%(eligible_supplier)s,%(organization)s,%(source_type)s,%(recurring)s,%(expected_date)s,%(notes)s,%(carry_eligible)s) RETURNING *""",f.model_dump()).fetchone()
        if has_new_rules:
            store_funding_eligibility(c, created["id"], rules)
        if f.received_cents:
            add_receipt(c,created["id"],f.received_cents,f.received_on)
        created = funding_rule_fields(created | funding_eligibility(c, created["id"]))
        audit(c,"created","funding",created["id"],created)
        return created

@router.patch("/funding/{funding_id}/received")
def confirm_funding(funding_id: int, r: Receipt):
    with db() as c:
        f=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(funding_id,)).fetchone()
        if not f: bad("Unknown funding")
        if not f["received_cents"] <= r.received_cents <= f["expected_cents"]: bad("Receipt must increase confirmed funding within award")
        updated=c.execute("UPDATE funding SET received_cents=%s WHERE id=%s RETURNING *",(r.received_cents,funding_id)).fetchone()
        if r.received_cents>f["received_cents"]:
            add_receipt(c,funding_id,r.received_cents-f["received_cents"],r.received_on)
        audit(c,"receipt_confirmed","funding",funding_id,{"before":f["received_cents"],"after":updated["received_cents"]})
        return funding_rule_fields(updated | funding_eligibility(c, funding_id))

@router.get("/funding")
def funding():
    with db() as c:
        rows = c.execute("""SELECT f.*, e.eligible_programs, e.eligible_suppliers, e.eligible_purchase_types,
        capacity_cents-COALESCE((SELECT sum(a.cents) FROM active_allocation a JOIN budget b ON b.id=a.budget_id WHERE b.funding_id=f.id),0) AS remaining_cents,
        capacity_cents-COALESCE((SELECT sum(b.cents) FROM budget b WHERE b.funding_id=f.id),0) AS unallocated_cents
        FROM funding_capacity f JOIN effective_funding_eligibility e ON e.funding_id=f.id ORDER BY f.id""").fetchall()
        return [funding_rule_fields(row) for row in rows]

@router.post("/budgets",status_code=201)
def add_budget(b: Budget):
    with db() as c:
        f=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(b.funding_id,)).fetchone()
        if not f: bad("Unknown funding")
        if not c.execute("SELECT 1 FROM program WHERE code=%s",(b.program_code,)).fetchone(): bad("Unknown program")
        if not restriction_allows(funding_eligibility(c, b.funding_id), "eligible_program", b.program_code):
            bad("Program not eligible")
        if f["expiry"] and f["expiry"] < date.today(): bad("Funding expired")
        used=c.execute("SELECT COALESCE(sum(cents),0) AS n FROM budget WHERE funding_id=%s",(b.funding_id,)).fetchone()["n"]
        if used+b.cents>capacity(c,f["id"]): bad("Insufficient unallocated confirmed funding")
        if c.execute("SELECT 1 FROM budget WHERE funding_id=%s AND program_code=%s",(b.funding_id,b.program_code)).fetchone(): bad("Budget already exists")
        created=c.execute("INSERT INTO budget(funding_id,program_code,cents) VALUES (%(funding_id)s,%(program_code)s,%(cents)s) RETURNING *",b.model_dump()).fetchone()
        audit(c,"created","budget",created["id"],created)
        return created

BUDGET_QUERY="""SELECT b.*, f.name AS funding_name,f.kind,f.academic_year,f.expiry,
 e.eligible_programs,e.eligible_suppliers,e.eligible_purchase_types,
 b.cents-COALESCE((SELECT sum(a.cents) FROM active_allocation a WHERE a.budget_id=b.id),0) AS remaining,
 f.capacity_cents-COALESCE((SELECT sum(a.cents) FROM active_allocation a JOIN budget bb ON bb.id=a.budget_id WHERE bb.funding_id=f.id),0) AS fund_remaining
 FROM budget b JOIN funding_capacity f ON f.id=b.funding_id
 JOIN effective_funding_eligibility e ON e.funding_id=f.id"""

@router.get("/budgets")
def budgets():
    with db() as c:
        return [funding_rule_fields(row) for row in c.execute(BUDGET_QUERY+" ORDER BY b.id")]

@router.post("/transactions",status_code=201)
def record(p: Purchase):
    with db() as c:
        c.execute("SELECT pg_advisory_xact_lock(2663001)")
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
    try: validate_purchase(p.cents,splits,p.purchase_date,p.supplier,p.purchase_type)
    except ValueError as e: bad(str(e))
    if c.execute("SELECT 1 FROM purchase p LEFT JOIN purchase_void v ON v.purchase_id=p.id WHERE v.purchase_id IS NULL AND p.purchase_date=%s AND lower(trim(p.supplier))=lower(trim(%s)) AND p.cents=%s",(p.purchase_date,p.supplier,p.cents)).fetchone() and not p.duplicate_reason.strip(): bad("Possible duplicate purchase; provide a review reason if legitimate")
    tx=c.execute("INSERT INTO purchase(purchase_date,supplier,purchase_type,description,cents) VALUES (%(purchase_date)s,%(supplier)s,%(purchase_type)s,%(description)s,%(cents)s) RETURNING *",p.model_dump()).fetchone()
    for a in p.allocations:
        c.execute("INSERT INTO allocation VALUES (%s,%s,%s)",(tx["id"],a.budget_id,a.cents))
    audit(c,"created","purchase",tx["id"],p.model_dump())
    return tx

@router.get("/transactions")
def transactions():
    with db() as c:
        return c.execute("""SELECT p.*, CASE WHEN v.purchase_id IS NULL THEN 'confirmed' ELSE 'voided' END AS status, v.reason AS void_reason, v.created_at AS voided_at, (SELECT replacement_id FROM purchase_correction WHERE original_id=p.id) AS replacement_id, (SELECT original_id FROM purchase_correction WHERE replacement_id=p.id) AS original_id, (SELECT json_agg(json_build_object('budget_id',a.budget_id,'program',b.program_code,'funding',f.name,'kind',f.kind,'academic_year',f.academic_year,'cents',a.cents) ORDER BY a.budget_id)
        FROM allocation a JOIN budget b ON b.id=a.budget_id JOIN funding f ON f.id=b.funding_id WHERE a.purchase_id=p.id) AS allocations FROM purchase p LEFT JOIN purchase_void v ON v.purchase_id=p.id ORDER BY p.purchase_date DESC,p.id DESC""").fetchall()

@router.get("/dashboard")
def dashboard(year: str = "2026-2027"):
    validate_year_label(year)
    with db() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
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
    purchase_type: str = Field(default="",max_length=100)

@router.post("/allocation-suggestions")
def allocate_suggestion(p: SuggestionRequest):
    validate_year_label(p.academic_year)
    with db() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        period=c.execute("SELECT * FROM academic_period WHERE academic_year=%s",(p.academic_year,)).fetchone()
        if period and not period["starts_on"] <= p.purchase_date <= period["ends_on"]: bad("Purchase date outside configured academic year")
        rows=c.execute(BUDGET_QUERY+" WHERE b.program_code=%s AND f.academic_year=%s",(p.program_code,p.academic_year)).fetchall()
        try:
            return suggest_allocations(rows,p.cents,p.program_code,p.academic_year,p.kind,p.supplier,p.purchase_date,p.preferred_funding,p.purchase_type)
        except ValueError as e:
            bad(str(e))

class ChangeReason(BaseModel):
    reason: str = Field(min_length=1,max_length=1000)

class FundingExpiryChange(ChangeReason):
    expiry: date | None

@router.patch("/funding/{funding_id}/expiry")
def change_funding_expiry(funding_id: int, change: FundingExpiryChange):
    reason = change.reason.strip()
    if not reason:
        bad("Reason required")

    with db() as c:
        funding = c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE", (funding_id,)).fetchone()
        if not funding:
            raise HTTPException(404, "Unknown funding")
        if funding["expiry"] == change.expiry:
            return funding_rule_fields(funding | funding_eligibility(c, funding_id))
        if c.execute(
            "SELECT 1 FROM active_funding_transfer WHERE source_id=%s OR destination_id=%s",
            (funding_id, funding_id),
        ).fetchone():
            bad("Reverse active transfers before changing expiry")
        if change.expiry and c.execute(
            """SELECT 1 FROM active_allocation a
               JOIN budget b ON b.id=a.budget_id
               JOIN purchase p ON p.id=a.purchase_id
               WHERE b.funding_id=%s AND p.purchase_date>%s""",
            (funding_id, change.expiry),
        ).fetchone():
            bad("Expiry conflicts with existing spending")

        updated = c.execute(
            "UPDATE funding SET expiry=%s WHERE id=%s RETURNING *", (change.expiry, funding_id)
        ).fetchone()
        audit(c, "expiry_changed", "funding", funding_id, {
            "before": funding["expiry"], "after": change.expiry, "reason": reason,
        })
        return funding_rule_fields(updated | funding_eligibility(c, funding_id))

class BudgetChange(ChangeReason):
    cents: int = Field(ge=0,le=10**12)

@router.post("/transactions/{purchase_id}/void")
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

@router.patch("/budgets/{budget_id}")
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
        if change.cents > b["cents"]:
            if f["expiry"] and f["expiry"] < date.today(): bad("Funding expired")
            if not restriction_allows(funding_eligibility(c, f["id"]), "eligible_program", b["program_code"]):
                bad("Program not eligible")
        result=c.execute("UPDATE budget SET cents=%s WHERE id=%s RETURNING *",(change.cents,budget_id)).fetchone()
        audit(c,"adjusted","budget",budget_id,{"before":b["cents"],"after":change.cents,"reason":change.reason.strip()})
        return result

@router.get("/audit")
def audit_history():
    with db() as c:
        return c.execute("SELECT * FROM audit_event ORDER BY id DESC LIMIT 500").fetchall()

def report_rows(year: str = "2026-2027", start: date | None = None, end: date | None = None, program: str | None = None, supplier: str | None = None, funding_id: int | None = None, purchase_type: str | None = None):
    from .reporting import validate_period
    validate_year_label(year)
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

@router.get("/reports/spending")
def spending_report(year: str = "2026-2027", start: date | None = None, end: date | None = None, program: str | None = None, supplier: str | None = None, funding_id: int | None = None, purchase_type: str | None = None):
    from .reporting import summarize
    return summarize(report_rows(year,start,end,program,supplier,funding_id,purchase_type))

@router.get("/reports/spending.xlsx")
def spending_export(year: str = "2026-2027", start: date | None = None, end: date | None = None, program: str | None = None, supplier: str | None = None, funding_id: int | None = None, purchase_type: str | None = None):
    from fastapi.responses import Response
    from .export import spending_workbook
    rows=report_rows(year,start,end,program,supplier,funding_id,purchase_type)
    content=spending_workbook(rows,{"Academic year":year,"Start":start,"End":end,"Program":program,"Supplier":supplier,"Funding ID":funding_id,"Purchase type":purchase_type})
    return Response(content,media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":'attachment; filename="asufc-spending.xlsx"',"Cache-Control":"no-store"})

class Correction(ChangeReason):
    replacement: Purchase

@router.post("/transactions/{purchase_id}/correct",status_code=201)
def correct_purchase(purchase_id: int, change: Correction):
    if not change.reason.strip(): bad("Reason required")
    with db() as c:
        c.execute("SELECT pg_advisory_xact_lock(2663001)")
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

@router.get("/funding/{funding_id}/receipts")
def receipts(funding_id: int):
    with db() as c:
        if not c.execute("SELECT 1 FROM funding WHERE id=%s",(funding_id,)).fetchone(): raise HTTPException(404,"Unknown funding")
        return c.execute("SELECT * FROM funding_receipt WHERE funding_id=%s ORDER BY id",(funding_id,)).fetchall()

def validate_year_label(year):
    if len(year)!=9 or year[4]!="-" or not year.isascii() or not year[:4].isdigit() or not year[5:].isdigit() or int(year[:4])<1 or int(year[5:])!=int(year[:4])+1:
        bad("Academic year must contain consecutive years, e.g. 2026-2027")

class AcademicPeriod(BaseModel):
    academic_year: str
    starts_on: date
    ends_on: date

class SemesterPeriod(BaseModel):
    name: str = Field(min_length=1,max_length=100)
    starts_on: date
    ends_on: date

@router.get("/academic-years")
def academic_years():
    with db() as c:
        return c.execute("SELECT p.*, COALESCE((SELECT json_agg(s ORDER BY s.starts_on) FROM semester s WHERE s.period_id=p.id),'[]'::json) AS semesters FROM academic_period p ORDER BY starts_on").fetchall()

@router.post("/academic-years",status_code=201)
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

@router.post("/academic-years/{year}/semesters",status_code=201)
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

@router.patch("/funding/{funding_id}/carry-permission")
def carry_permission(funding_id: int,p: CarryPermission):
    if not p.reason.strip(): bad("Reason required")
    with db() as c:
        old=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(funding_id,)).fetchone()
        if not old: raise HTTPException(404,"Unknown funding")
        row=c.execute("UPDATE funding SET carry_eligible=%s WHERE id=%s RETURNING *",(p.eligible,funding_id)).fetchone()
        audit(c,"carry_permission_changed","funding",funding_id,{"before":old["carry_eligible"],"after":p.eligible,"reason":p.reason.strip()})
        return funding_rule_fields(row | funding_eligibility(c, funding_id))

@router.post("/funding/{funding_id}/carry-forward",status_code=201)
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
        store_funding_eligibility(c, dest["id"], funding_eligibility(c, funding_id))
        transfer=c.execute("INSERT INTO funding_transfer(source_id,destination_id,cents,reason) VALUES (%s,%s,%s,%s) RETURNING *",(funding_id,dest["id"],p.cents,p.reason.strip())).fetchone()
        audit(c,"carried_forward","funding",funding_id,transfer)
        return transfer

@router.get("/funding-transfers")
def funding_transfers():
    with db() as c:
        return c.execute("SELECT t.*,s.academic_year AS source_year,d.academic_year AS destination_year,s.name AS funding_name,s.kind,v.transfer_id IS NOT NULL AS reversed,v.reason AS reversal_reason FROM funding_transfer t JOIN funding s ON s.id=t.source_id JOIN funding d ON d.id=t.destination_id LEFT JOIN funding_transfer_void v ON v.transfer_id=t.id ORDER BY t.id DESC").fetchall()

@router.get("/reports/reconciliation")
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

@router.get("/reports/reconciliation.xlsx")
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
    c.execute("SELECT pg_advisory_xact_lock(2663001)")
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

@router.post("/imports/preview")
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

@router.post("/imports/commit",status_code=201)
def commit_import(p: ImportWorkbook):
    parsed=parse_import(p)
    with db() as c:
        result=import_rows(c,parsed)
        audit(c,"imported","purchase",result[0],{"purchase_ids":result})
        return {"imported":len(result),"purchase_ids":result}

class NewProgram(BaseModel):
    code: str = Field(pattern=r"^[A-Z0-9&_-]{2,40}$")
    name: str = Field(min_length=1,max_length=200)

@router.post("/programs",status_code=201)
def create_program(p: NewProgram):
    if not p.name.strip(): bad("Name required")
    with db() as c:
        row=c.execute("INSERT INTO program(code,name) VALUES (%s,%s) ON CONFLICT DO NOTHING RETURNING *",(p.code,p.name.strip())).fetchone()
        if not row: raise HTTPException(409,"Program code already exists")
        return row

@router.post("/funding-transfers/{transfer_id}/reverse")
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

class PeriodEdit(ChangeReason):
    starts_on: date
    ends_on: date

class SemesterEdit(PeriodEdit):
    name: str = Field(min_length=1,max_length=100)

@router.patch("/academic-years/{year}")
def edit_academic_year(year: str,p: PeriodEdit):
    validate_year_label(year)
    if not p.reason.strip() or p.starts_on>p.ends_on or p.starts_on.year!=int(year[:4]) or p.ends_on.year!=int(year[5:]): bad("Valid dates and reason required")
    with db() as c:
        c.execute("LOCK TABLE funding IN EXCLUSIVE MODE")
        c.execute("LOCK TABLE academic_period IN SHARE ROW EXCLUSIVE MODE")
        old=c.execute("SELECT * FROM academic_period WHERE academic_year=%s FOR UPDATE",(year,)).fetchone()
        if not old: raise HTTPException(404,"Unknown academic year")
        if c.execute("SELECT 1 FROM academic_period WHERE id<>%s AND starts_on<=%s AND ends_on>=%s",(old["id"],p.ends_on,p.starts_on)).fetchone(): bad("Academic years cannot overlap")
        if c.execute("SELECT 1 FROM semester WHERE period_id=%s AND (starts_on<%s OR ends_on>%s)",(old["id"],p.starts_on,p.ends_on)).fetchone(): bad("Existing semester outside new dates")
        if c.execute("SELECT 1 FROM purchase p JOIN active_allocation a ON a.purchase_id=p.id JOIN budget b ON b.id=a.budget_id JOIN funding f ON f.id=b.funding_id WHERE f.academic_year=%s AND (p.purchase_date<%s OR p.purchase_date>%s)",(year,p.starts_on,p.ends_on)).fetchone(): bad("Existing purchase outside new dates")
        if c.execute("SELECT 1 FROM active_funding_transfer t JOIN funding f ON f.id=t.source_id OR f.id=t.destination_id WHERE f.academic_year=%s",(year,)).fetchone(): bad("Reverse active transfers before changing year dates")
        row=c.execute("UPDATE academic_period SET starts_on=%s,ends_on=%s WHERE id=%s RETURNING *",(p.starts_on,p.ends_on,old["id"])).fetchone()
        audit(c,"adjusted","academic_year",old["id"],{"before":old,"after":row,"reason":p.reason})
        return row

@router.patch("/academic-years/{year}/semesters/{semester_id}")
def edit_semester(year: str,semester_id: int,p: SemesterEdit):
    with db() as c:
        period=c.execute("SELECT * FROM academic_period WHERE academic_year=%s FOR UPDATE",(year,)).fetchone()
        if not period: raise HTTPException(404,"Unknown academic year")
        old=c.execute("SELECT * FROM semester WHERE id=%s AND period_id=%s",(semester_id,period["id"])).fetchone()
        if not old: raise HTTPException(404,"Unknown semester")
        if not p.reason.strip() or not p.name.strip() or not period["starts_on"]<=p.starts_on<=p.ends_on<=period["ends_on"]: bad("Valid semester dates, name and reason required")
        if c.execute("SELECT 1 FROM semester WHERE period_id=%s AND id<>%s AND (name=%s OR (starts_on<=%s AND ends_on>=%s))",(period["id"],semester_id,p.name.strip(),p.ends_on,p.starts_on)).fetchone(): bad("Duplicate or overlapping semester")
        row=c.execute("UPDATE semester SET name=%s,starts_on=%s,ends_on=%s WHERE id=%s RETURNING *",(p.name.strip(),p.starts_on,p.ends_on,semester_id)).fetchone()
        audit(c,"adjusted","semester",semester_id,{"before":old,"after":row,"reason":p.reason})
        return row

class FundingEligibilityChange(ChangeReason):
    eligible_programs: list[ProgramCode] = Field(max_length=100)
    eligible_suppliers: list[SupplierName] = Field(max_length=100)
    eligible_purchase_types: list[PurchaseType] = Field(max_length=100)
    expected: dict[str, list[str]] = Field(max_length=3)

def lock_funding_eligibility(c, funding_id: int):
    if not c.execute("SELECT id FROM funding WHERE id=%s FOR UPDATE", (funding_id,)).fetchone():
        raise HTTPException(404, "Unknown funding")
    return funding_eligibility(c, funding_id)

def change_funding_eligibility(c, funding_id: int, previous: dict, rules: dict, reason: str):
    if rules == previous:
        return
    if c.execute(
        "SELECT 1 FROM active_funding_transfer WHERE source_id=%s OR destination_id=%s",
        (funding_id, funding_id),
    ).fetchone():
        bad("Reverse active transfers before changing restrictions")
    programs = rules["eligible_programs"]
    verify_eligible_programs(c, programs)
    if programs and c.execute(
        "SELECT 1 FROM budget WHERE funding_id=%s AND cents>0 AND NOT (program_code=ANY(%s))",
        (funding_id, programs),
    ).fetchone():
        bad("Restriction conflicts with existing budget allocations")
    if any(rules.values()):
        purchases = c.execute("""SELECT DISTINCT b.program_code, p.supplier, p.purchase_type
            FROM active_allocation a JOIN budget b ON b.id=a.budget_id
            JOIN purchase p ON p.id=a.purchase_id WHERE b.funding_id=%s""", (funding_id,))
        for purchase in purchases:
            if spending_restriction(rules, purchase["program_code"], purchase["supplier"], purchase["purchase_type"]):
                bad("Restriction conflicts with existing spending")
    store_funding_eligibility(c, funding_id, rules)
    audit(c, "restriction_changed", "funding", funding_id, {"before": previous, "after": rules, "reason": reason})

@router.patch("/funding/{funding_id}/eligibility")
def update_eligibility(funding_id: int, change: FundingEligibilityChange):
    reason = change.reason.strip()
    if not reason: bad("Reason required")
    rules = normalize_eligibility(change.eligible_programs, change.eligible_suppliers, change.eligible_purchase_types)
    with db() as c:
        previous = lock_funding_eligibility(c, funding_id)
        if previous != change.expected:
            raise HTTPException(409, "Spending rules changed. Reload the funding record and review the latest rules.")
        change_funding_eligibility(c, funding_id, previous, rules, reason)
        return {"funding_id": funding_id, **rules}

class PurchaseTypeRestriction(ChangeReason):
    purchase_type: str | None = Field(default=None, max_length=100)

@router.patch("/funding/{funding_id}/purchase-type")
def purchase_type_restriction(funding_id: int, change: PurchaseTypeRestriction):
    reason = change.reason.strip()
    if not reason: bad("Reason required")
    restriction = change.purchase_type.strip() if change.purchase_type is not None else None
    if restriction == "": bad("Restriction cannot be blank")
    with db() as c:
        previous = lock_funding_eligibility(c, funding_id)
        if len(previous["eligible_purchase_types"]) > 1:
            bad("Edit multiple purchase types using the spending rules form")
        rules = previous | {"eligible_purchase_types": [restriction] if restriction else []}
        change_funding_eligibility(c, funding_id, previous, rules, reason)
        return {"funding_id": funding_id, "purchase_type": restriction}

class PasswordChange(BaseModel):
    current_password: str = Field(max_length=1024)
    new_password: str = Field(max_length=1024)

@router.post("/auth/password")
def change_password(p: PasswordChange, request: Request, response: Response):
    try: validate_password(p.new_password)
    except ValueError as e: raise HTTPException(422,str(e))
    user=os.environ.get("STAFF_USER","staff")
    with db() as c:
        c.execute("SELECT pg_advisory_xact_lock(2663002)")
        if not c.execute("SELECT 1 FROM staff_session WHERE token_hash=%s AND expires_at>now()",(token_hash(request.cookies[COOKIE]),)).fetchone(): raise HTTPException(401,"Staff session expired")
        credential=c.execute("SELECT password_hash FROM staff_credential WHERE username=%s",(user,)).fetchone()
        c.execute("DELETE FROM staff_login_attempt WHERE attempted_at<now()-interval '15 minutes'")
        if c.execute("SELECT count(*) AS n FROM staff_login_attempt").fetchone()["n"]>=10: raise HTTPException(429,"Too many attempts")
        valid=verify_password(p.current_password,credential["password_hash"])
        if not valid: c.execute("INSERT INTO staff_login_attempt DEFAULT VALUES")
        else:
            if p.current_password==p.new_password: raise HTTPException(422,"Choose a different password")
            c.execute("UPDATE staff_credential SET password_hash=%s,updated_at=now() WHERE username=%s",(hash_password(p.new_password),user))
            c.execute("DELETE FROM staff_session")
            c.execute("DELETE FROM staff_login_attempt")
            audit(c,"password_changed","staff_account",0,{})
    if not valid: raise HTTPException(401,"Current password incorrect")
    response.delete_cookie(COOKIE,path="/",secure=os.getenv("SESSION_SECURE","1")!="0",httponly=True,samesite="strict")
    return {"ok":True}

register_receipts(router, db, audit, staff)
app.include_router(router)
