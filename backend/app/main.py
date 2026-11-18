import os
import secrets
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from typing import Literal
import psycopg
from psycopg.rows import dict_row
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

class Receipt(BaseModel):
    received_cents: int = Field(ge=0,le=10**12)

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
        if f.eligible_program and not c.execute("SELECT 1 FROM program WHERE code=%s",(f.eligible_program,)).fetchone(): bad("Unknown program")
        return c.execute("""INSERT INTO funding(name,academic_year,kind,expected_cents,received_cents,expiry,eligible_program,eligible_supplier)
         VALUES (%(name)s,%(academic_year)s,%(kind)s,%(expected_cents)s,%(received_cents)s,%(expiry)s,%(eligible_program)s,%(eligible_supplier)s) RETURNING *""",f.model_dump()).fetchone()

@app.patch("/funding/{funding_id}/received")
def confirm_funding(funding_id: int, r: Receipt):
    with db() as c:
        f=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(funding_id,)).fetchone()
        if not f: bad("Unknown funding")
        if not f["received_cents"] <= r.received_cents <= f["expected_cents"]: bad("Receipt must increase confirmed funding within award")
        return c.execute("UPDATE funding SET received_cents=%s WHERE id=%s RETURNING *",(r.received_cents,funding_id)).fetchone()

@app.get("/funding")
def funding():
    with db() as c:
        return c.execute("""SELECT f.*, received_cents-COALESCE((SELECT sum(a.cents) FROM allocation a JOIN budget b ON b.id=a.budget_id WHERE b.funding_id=f.id),0) AS remaining_cents,
        received_cents-COALESCE((SELECT sum(b.cents) FROM budget b WHERE b.funding_id=f.id),0) AS unallocated_cents FROM funding f ORDER BY id""").fetchall()

@app.post("/budgets",status_code=201)
def add_budget(b: Budget):
    with db() as c:
        f=c.execute("SELECT * FROM funding WHERE id=%s FOR UPDATE",(b.funding_id,)).fetchone()
        if not f: bad("Unknown funding")
        if not c.execute("SELECT 1 FROM program WHERE code=%s",(b.program_code,)).fetchone(): bad("Unknown program")
        if f["eligible_program"] and f["eligible_program"] != b.program_code: bad("Program not eligible")
        if f["expiry"] and f["expiry"] < date.today(): bad("Funding expired")
        used=c.execute("SELECT COALESCE(sum(cents),0) AS n FROM budget WHERE funding_id=%s",(b.funding_id,)).fetchone()["n"]
        if used+b.cents>f["received_cents"]: bad("Insufficient unallocated confirmed funding")
        if c.execute("SELECT 1 FROM budget WHERE funding_id=%s AND program_code=%s",(b.funding_id,b.program_code)).fetchone(): bad("Budget already exists")
        return c.execute("INSERT INTO budget(funding_id,program_code,cents) VALUES (%(funding_id)s,%(program_code)s,%(cents)s) RETURNING *",b.model_dump()).fetchone()

BUDGET_QUERY="""SELECT b.*, f.name AS funding_name,f.kind,f.academic_year,f.expiry,f.eligible_program,f.eligible_supplier,
 b.cents-COALESCE((SELECT sum(a.cents) FROM allocation a WHERE a.budget_id=b.id),0) AS remaining,
 f.received_cents-COALESCE((SELECT sum(a.cents) FROM allocation a JOIN budget bb ON bb.id=a.budget_id WHERE bb.funding_id=f.id),0) AS fund_remaining
 FROM budget b JOIN funding f ON f.id=b.funding_id"""

@app.get("/budgets")
def budgets():
    with db() as c:
        return c.execute(BUDGET_QUERY+" ORDER BY b.id").fetchall()

@app.post("/transactions",status_code=201)
def record(p: Purchase):
    with db() as c:
        ids=[a.budget_id for a in p.allocations]
        # Serialize writers by funding source, then read fresh balances.
        c.execute("SELECT id FROM funding WHERE id IN (SELECT funding_id FROM budget WHERE id=ANY(%s)) ORDER BY id FOR UPDATE",(ids,)).fetchall()
        rows={r["id"]:r for r in c.execute(BUDGET_QUERY+" WHERE b.id=ANY(%s)",(ids,)).fetchall()}
        if any(i not in rows for i in ids): bad("Unknown budget")
        splits=[{**rows[a.budget_id],**a.model_dump()} for a in p.allocations]
        try: validate_purchase(p.cents,splits,p.purchase_date,p.supplier)
        except ValueError as e: bad(str(e))
        tx=c.execute("INSERT INTO purchase(purchase_date,supplier,purchase_type,description,cents) VALUES (%(purchase_date)s,%(supplier)s,%(purchase_type)s,%(description)s,%(cents)s) RETURNING *",p.model_dump()).fetchone()
        for a in p.allocations:
            c.execute("INSERT INTO allocation VALUES (%s,%s,%s)",(tx["id"],a.budget_id,a.cents))
        return tx

@app.get("/transactions")
def transactions():
    with db() as c:
        return c.execute("""SELECT p.*, (SELECT json_agg(json_build_object('budget_id',a.budget_id,'program',b.program_code,'funding',f.name,'kind',f.kind,'academic_year',f.academic_year,'cents',a.cents) ORDER BY a.budget_id)
        FROM allocation a JOIN budget b ON b.id=a.budget_id JOIN funding f ON f.id=b.funding_id WHERE a.purchase_id=p.id) AS allocations FROM purchase p ORDER BY p.purchase_date DESC,p.id DESC""").fetchall()

@app.get("/dashboard")
def dashboard(year: str = "2026-2027"):
    with db() as c:
        return {"funding":c.execute("""SELECT kind, sum(received_cents) AS received, sum(expected_cents-received_cents) AS expected,
        sum(COALESCE((SELECT sum(a.cents) FROM allocation a JOIN budget b ON b.id=a.budget_id WHERE b.funding_id=f.id),0)) AS spent
        FROM funding f WHERE academic_year=%s GROUP BY kind""",(year,)).fetchall(),
        "programs":c.execute("""SELECT b.program_code, sum(b.cents) AS allocated,
        sum(COALESCE((SELECT sum(a.cents) FROM allocation a WHERE a.budget_id=b.id),0)) AS spent FROM budget b JOIN funding f ON f.id=b.funding_id WHERE f.academic_year=%s GROUP BY b.program_code""",(year,)).fetchall()}


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
