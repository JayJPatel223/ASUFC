from datetime import date

def validate_purchase(total: int, allocations: list[dict], purchase_date: date, supplier: str):
    if total <= 0 or not allocations or sum(a["cents"] for a in allocations) != total:
        raise ValueError("Allocations must equal a positive purchase total")
    if len({a["budget_id"] for a in allocations}) != len(allocations):
        raise ValueError("Duplicate budget allocation")
    if len({a["academic_year"] for a in allocations}) != 1:
        raise ValueError("Cannot split across academic years")
    for a in allocations:
        if a["cents"] <= 0 or a["cents"] > a["remaining"]:
            raise ValueError("Insufficient budget")
        if a["expiry"] and (purchase_date > a["expiry"] or date.today() > a["expiry"]):
            raise ValueError("Funding expired")
        if a["eligible_program"] and a["eligible_program"] != a["program_code"]:
            raise ValueError("Program not eligible")
        if a["eligible_supplier"] and a["eligible_supplier"].casefold() != supplier.casefold():
            raise ValueError("Supplier not eligible")
    for fund in {a["funding_id"] for a in allocations}:
        group = [a for a in allocations if a["funding_id"] == fund]
        if sum(a["cents"] for a in group) > group[0]["fund_remaining"]:
            raise ValueError("Insufficient confirmed funding")
