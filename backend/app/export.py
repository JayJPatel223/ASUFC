from io import BytesIO
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter
from .reporting import summarize

def text_cell(value):
    # Force untrusted spreadsheet text to remain text, not a formula.
    return str(value) if value is not None else ""

def spending_workbook(rows, filters):
    rows=list(rows)
    report=summarize(rows)
    wb=Workbook()
    ws=wb.active
    ws.title="Summary"
    ws.append(["ASUFC spending report", "CAD"])
    for key,value in filters.items():
        ws.append([key,text_cell(value)])
    ws.append(["Cash spent",report["totals"]["cash_cents"]/100])
    ws.append(["Credit used",report["totals"]["credit_cents"]/100])
    ws.append(["Distinct purchases",report["purchase_count"]])
    for row in ws.iter_rows():
        if row[0].value in ("Cash spent","Credit used"):
            row[1].number_format='"$"#,##0.00'
    for group in ("month","program","supplier","funding"):
        sh=wb.create_sheet(group.title())
        sh.append(["Group","Cash spent (CAD)","Credit used (CAD)"])
        for r in report[group]:
            sh.append([r["label"],r["cash_cents"]/100,r["credit_cents"]/100])
        for row in sh.iter_rows(min_row=2,min_col=2,max_col=3):
            for cell in row: cell.number_format='"$"#,##0.00'
    sh=wb.create_sheet("Allocations")
    sh.append(["Purchase ID","Date","Program","Supplier","Purchase type","Description","Funding ID","Funding source","Payment type","Allocation (CAD)"])
    for r in rows:
        sh.append([r["purchase_id"],r["purchase_date"],r["program_code"],r["supplier"],r.get("purchase_type",""),r.get("description",""),r["funding_id"],r["funding_name"],r["kind"],r["cents"]/100])
        sh.cell(sh.max_row,2).number_format="yyyy-mm-dd"
        sh.cell(sh.max_row,10).number_format='"$"#,##0.00'
    for sheet in wb:
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value,str): cell.data_type="s"
        for cell in sheet[1]:
            cell.font=Font(bold=True,color="FFFFFF")
            cell.fill=PatternFill("solid",fgColor="702D42")
        sheet.freeze_panes="A2"
        for col in sheet.columns:
            sheet.column_dimensions[get_column_letter(col[0].column)].width=min(48,max(14,max(len(str(c.value or "")) for c in col)+2))
        if sheet.title!="Summary": sheet.auto_filter.ref=sheet.dimensions
    out=BytesIO()
    wb.save(out)
    return out.getvalue()
