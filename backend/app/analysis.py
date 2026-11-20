"""Calculate read-only financial facts from the recorded ledger."""

from calendar import monthrange
from datetime import date, timedelta


def forecast(months, today, start, end):
    """Estimate the next full month from six consecutive populated months."""
    result = {
        "estimate": None, "months": [],
        "status": "An estimate needs spending in each of the last six complete months in this academic year.",
    }
    if not start or not end:
        return result | {"status": "Configure the financial year dates to make a forecast available."}
    last = today.replace(day=1) - timedelta(days=1)
    first_of_next = today.replace(day=monthrange(today.year, today.month)[1]) + timedelta(days=1)
    if first_of_next < start or first_of_next.replace(day=monthrange(first_of_next.year, first_of_next.month)[1]) > end:
        return result | {"status": "The next complete month falls outside this financial year."}
    by_month = {row["label"]: row for row in months}
    history = []
    for _ in range(6):
        month = last.isoformat()[:7]
        row = by_month.get(month)
        first = last.replace(day=1)
        if first < start or last > end or not row or row["cash_cents"] + row["credit_cents"] == 0:
            return result
        history.append(row)
        last = first - timedelta(days=1)
    estimate = {key: (sum(row[key] for row in history) + 3) // 6 for key in ("cash_cents", "credit_cents")}
    return {
        "estimate": {"label": first_of_next.isoformat()[:7], **estimate},
        "months": [row["label"] for row in reversed(history)],
        "status": "Estimate based on the average recorded spending in six complete months.",
    }


def analyze(spending, budgets, sources, period, today):
    balances = {
        kind: {"allocated_cents": 0, "spent_cents": 0, "budget_remaining_cents": 0, "funding_remaining_cents": 0}
        for kind in ("cash", "credit")
    }
    programs = {}
    for row in budgets:
        amount = int(row["cents"])
        remaining = int(row["remaining"])
        group = balances[row["kind"]]
        group["allocated_cents"] += amount
        group["spent_cents"] += amount - remaining
        group["budget_remaining_cents"] += remaining
        program = programs.setdefault((row["program_code"], row["kind"]), {"allocated_cents": 0, "spent_cents": 0})
        program["allocated_cents"] += amount
        program["spent_cents"] += amount - remaining
    for source in sources:
        balances[source["kind"]]["funding_remaining_cents"] += int(source["remaining_cents"])
        cutoff = source["expiry"]
        remaining = int(source["remaining_cents"])
        source["days_to_expiry"] = (cutoff - today).days if cutoff else None
        source["low_balance"] = int(source["capacity_cents"]) > 0 and remaining * 100 <= source["capacity_cents"] * 15
        source["unreceived_cents"] = source["expected_cents"] - source["received_cents"]
    previous = (today.replace(day=1) - timedelta(days=1)).isoformat()[:7]
    return {
        "spending": spending,
        "previous_month": next((row for row in spending["month"] if row["label"] == previous),
                               {"label": previous, "cash_cents": 0, "credit_cents": 0}),
        "balances": balances,
        "funding": sources,
        "programs": [
            {"code": code, "kind": kind, **values}
            for (code, kind), values in sorted(programs.items())
        ],
        "forecast": forecast(spending["month"], today, period.get("starts_on"), period.get("ends_on")),
    }
