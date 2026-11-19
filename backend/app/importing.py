"""Parse a limited, explicitly mapped XLSX ledger; no writes."""
from io import BytesIO
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from zipfile import ZipFile
from openpyxl import load_workbook

FIELDS=("external_id","purchase_date","supplier","purchase_type","description","amount","budget_id")

def parse_workbook(content, sheet, mapping):
    if len(content)>5_000_000: raise ValueError("Workbook exceeds 5 MB")
    if set(mapping)!=set(FIELDS) or len(set(mapping.values()))!=len(FIELDS):
        raise ValueError("Map all seven fields to distinct column headers")
    try:
        with ZipFile(BytesIO(content)) as z:
            if sum(i.file_size for i in z.infolist())>30_000_000: raise ValueError("Expanded workbook too large")
        wb=load_workbook(BytesIO(content),read_only=True,data_only=False,keep_links=False)
    except Exception as e:
        raise ValueError("Invalid or oversized XLSX workbook") from e
    try:
        if sheet not in wb.sheetnames: raise ValueError("Unknown worksheet")
        ws=wb[sheet]
        if ws.max_row and ws.max_row>1001 or ws.max_column and ws.max_column>100: raise ValueError("Maximum 1000 rows and 100 columns")
        it=ws.iter_rows(max_row=min(ws.max_row or 1001,1001),max_col=min(ws.max_column or 100,100))
        headers=[str(c.value or "").strip() for c in next(it,[])]
        if any(headers.count(v)!=1 for v in mapping.values()): raise ValueError("Mapped headers must exist exactly once")
        indices={k:headers.index(v) for k,v in mapping.items()}
        rows=[]; errors=[]; seen=set()
        for n,cells in enumerate(it,2):
            if all(c.value is None for c in cells): continue
            try:
                if any(cells[i].data_type=="f" for i in indices.values()): raise ValueError("Formulas are not accepted in mapped fields")
                v={k:cells[i].value for k,i in indices.items()}
                ident=str(v["external_id"] or "").strip()
                if not ident or len(ident)>200 or ident in seen: raise ValueError("Missing or duplicate external ID")
                d=v["purchase_date"]
                d=d.date() if isinstance(d,datetime) else d if isinstance(d,date) else date.fromisoformat(str(d))
                amount=Decimal(str(v["amount"]))*100
                if not amount.is_finite() or amount!=amount.to_integral_value() or not 0<amount<=10**12: raise ValueError("Invalid CAD amount")
                budget=Decimal(str(v["budget_id"]))
                if not budget.is_finite() or budget!=budget.to_integral_value() or not 0<budget<=2**63-1: raise ValueError("Invalid budget ID")
                supplier=str(v["supplier"] or "").strip(); kind=str(v["purchase_type"] or "").strip()
                description=str(v["description"] or "")
                if not supplier or len(supplier)>200 or not kind or len(kind)>100 or len(description)>1000: raise ValueError("Invalid supplier, type or description")
                seen.add(ident)
                rows.append(dict(row=n,external_id=ident,purchase_date=d.isoformat(),supplier=supplier,purchase_type=kind,description=description,cents=int(amount),allocations=[dict(budget_id=int(budget),cents=int(amount))]))
            except (ValueError,InvalidOperation,TypeError,OverflowError) as e:
                errors.append(dict(row=n,error=str(e)))
        return dict(rows=rows,errors=errors)
    finally: wb.close()
