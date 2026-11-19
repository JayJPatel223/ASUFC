from collections import defaultdict
from datetime import date

def summarize(rows):
    """Aggregate allocation-level rows, never count purchase totals per split."""
    groups = {k: defaultdict(lambda: {"cash_cents": 0, "credit_cents": 0}) for k in ("month", "program", "supplier", "funding")}
    total = {"cash_cents": 0, "credit_cents": 0}
    purchases = set()
    for r in rows:
        key = r["kind"] + "_cents"
        amount = int(r["cents"])
        total[key] += amount
        purchases.add(r["purchase_id"])
        labels = {"month": r["purchase_date"].isoformat()[:7], "program": r["program_code"], "supplier": r["supplier"], "funding": str(r["funding_id"]) + " · " + r["funding_name"]}
        for group, label in labels.items():
            groups[group][label][key] += amount
    return {"totals": total, "purchase_count": len(purchases), **{group: [{"label": label, **values} for label, values in sorted(items.items())] for group, items in groups.items()}}

def validate_period(start, end):
    if start and end and start > end:
        raise ValueError("Start date must precede end date")
