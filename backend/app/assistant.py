"""Classify staff questions locally and present scoped, deterministic ledger facts."""

from collections import Counter
from math import log, sqrt
import re
from typing import Literal

Topic = Literal[
    "overview", "cash_balance", "credit_balance", "budget_balance", "year_spending", "last_month",
    "expiring", "unused", "expected", "program_comparison", "allocation", "estimate",
]

EXAMPLES: dict[Topic, tuple[str, ...]] = {
    "overview": (
        "summarize our current financial situation", "give me a financial overview", "recap the ledger",
        "show a funding and spending summary", "what is our overall financial position",
    ),
    "cash_balance": (
        "how much cash funding remains", "what is the cash balance left", "cash still available",
        "how much money is left in cash", "remaining cash funding",
    ),
    "credit_balance": (
        "how much purchasing credit is left", "what is the credit balance", "how many credits remain",
        "available buying credits", "remaining purchasing credits",
    ),
    "budget_balance": (
        "how much remains for the breakfast program", "how much do we have left for general restocks",
        "what is left in the program budget", "remaining program budget", "what can breakfast still spend",
        "how much is left for breakfast", "how much is left for events", "budget balance for this program",
    ),
    "year_spending": (
        "how much have we spent this academic year", "total spending this year", "how much did we spend so far",
        "what have we spent year to date", "show annual expense totals", "confirmed purchases this year",
    ),
    "last_month": (
        "how much did we spend last month", "previous month spending", "total expenses for last month",
        "what did we spend the prior month", "last month's purchase totals",
    ),
    "expiring": (
        "which funding sources expire soon", "what grants are expiring next", "upcoming grant expiry dates",
        "funds that expire within 30 days", "what is due to expire soon",
    ),
    "unused": (
        "which funding sources have unused balances", "show grants with money left over",
        "which sources still have an unspent balance", "list unused funding", "where are our unspent funds",
    ),
    "expected": (
        "which grants have not been received yet", "show pending donations and outstanding grants",
        "what funding are we still waiting for", "show expected funds", "which credits were not received",
        "what money are we still expecting", "what donations are still expected",
    ),
    "program_comparison": (
        "compare spending across programs", "which programs have the highest spending", "rank programs by spending",
        "compare the program budgets", "program breakdown by amount spent",
    ),
    "allocation": (
        "where could available funding be utilized", "what grant can pay for a purchase", "recommend funding for an expense",
        "help me find eligible allocations", "can I bill an order to a funding source",
    ),
    "estimate": (
        "forecast spending next month", "estimate next month's expenses", "what is the spending projection",
        "project our future spending", "predict next month expenses",
    ),
}
COMMON = frozenset("a am an are can could did do does for give have how i in is it me much of on our the to we were what which will with yet".split())
PROGRAM_ALIASES = {
    "ASUFCGR": ("general restocks",),
    "ASUFCFSBP": ("breakfast", "foodsharing"),
    "ASUFCE&W": ("events", "workshops"),
    "ASUFCSIR": ("specialty", "specialty restocks"),
}
SOURCE_TOPICS = {"expiring", "unused", "expected"}


def words(text):
    return re.findall(r"[a-z0-9]+", text.casefold())


def features(text):
    tokens = [token for token in words(text) if token not in COMMON]
    return set(tokens) | {" ".join(pair) for pair in zip(tokens, tokens[1:])}


class IntentModel:
    def __init__(self, examples):
        samples = [(topic, features(text)) for topic, group in examples.items() for text in group]
        occurrences = Counter(term for _, terms in samples for term in terms)
        self.weights = {term: log((1 + len(samples)) / (1 + seen)) + 1 for term, seen in occurrences.items()}
        self.samples = [(topic, self.vector(terms)) for topic, terms in samples]

    def vector(self, terms):
        weighted = {term: self.weights[term] for term in terms if term in self.weights}
        length = sqrt(sum(weight * weight for weight in weighted.values()))
        return {term: weight / length for term, weight in weighted.items()}

    def predict(self, question):
        query = self.vector(features(question))
        if not query:
            return None
        scores = {}
        for topic, sample in self.samples:
            score = sum(weight * sample.get(term, 0) for term, weight in query.items())
            scores[topic] = max(scores.get(topic, 0), score)
        (best, score), (_, second), *_ = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
        return best if score >= 0.38 and score - second >= 0.06 else None


MODEL = IntentModel(EXAMPLES)


def mentioned_programs(question, programs):
    normalized = " " + " ".join(words(question)) + " "
    found = []
    for program in programs:
        names = [program["name"], program["code"], *PROGRAM_ALIASES.get(program["code"], ())]
        if any(" " + " ".join(words(name)) + " " in normalized for name in names):
            found.append(program["code"])
    return found


def money(cents):
    whole, fraction = divmod(abs(int(cents)), 100)
    return f"{'-' if cents < 0 else ''}${whole:,}.{fraction:02d}"


def payment_totals(totals):
    return [f"Cash · {money(totals['cash_cents'])}", f"Purchasing credits · {money(totals['credit_cents'])}"]


def answer(topic, ledger, program, names):
    totals = ledger["spending"]["totals"]
    balances = ledger["balances"]
    scoped_balance = "budget_remaining_cents" if program else "funding_remaining_cents"
    if topic in SOURCE_TOPICS and program:
        return "Funding source details", ["Choose All programs to see source-level receipts, balances and expiry dates."], "Funding & grants"
    if topic == "allocation":
        return "Find eligible funding", [
            "Open Transactions and enter the purchase date, supplier, purchase type, program and amount.",
            "Use Suggest allocations to check eligible budget lines and review the suggested split before saving.",
        ], "Transactions"
    if topic == "cash_balance" or topic == "credit_balance":
        kind = "cash" if topic == "cash_balance" else "credit"
        title = "Recorded cash balance" if kind == "cash" else "Recorded purchasing credit balance"
        detail = "Available in the program's allocated budgets" if program else "Remaining across recorded funding sources"
        return title, [f"{detail} · {money(balances[kind][scoped_balance])}"], "Financial insights"
    if topic == "budget_balance":
        return "Remaining allocated budgets", payment_totals({
            kind + "_cents": balances[kind]["budget_remaining_cents"] for kind in ("cash", "credit")
        }), "Financial insights"
    if topic == "year_spending":
        return "Confirmed spending this academic year", payment_totals(totals), "Reports"
    if topic == "last_month":
        month = ledger["previous_month"]
        return "Confirmed spending in " + month["label"], payment_totals(month), "Reports"
    if topic == "program_comparison":
        rows = sorted(ledger["programs"], key=lambda row: (-row["spent_cents"], row["code"], row["kind"]))
        facts = [f"{names[row['code']]} · {row['kind']} · {money(row['spent_cents'])} spent" for row in rows]
        return "Program spending", facts or ["No program budgets match this selection."], "Financial insights"
    if topic == "estimate":
        forecast = ledger["forecast"]
        estimate = forecast["estimate"]
        if estimate:
            return "Spending estimate for " + estimate["label"], payment_totals(estimate) + [forecast["status"]], "Financial insights"
        return "Spending estimate unavailable", [forecast["status"]], "Financial insights"
    if topic in SOURCE_TOPICS:
        rows = ledger["funding"]
        if topic == "expiring":
            facts = [f"{row['name']} · {row['expiry']} · {money(row['remaining_cents'])} {row['kind']} left" for row in rows
                     if row["remaining_cents"] > 0 and row["days_to_expiry"] is not None and 0 <= row["days_to_expiry"] <= 30]
            return "Funding expiring within 30 days", facts or ["No sources with a remaining balance expire within 30 days."], "Funding & grants"
        if topic == "expected":
            facts = [f"{row['name']} · {money(row['unreceived_cents'])} {row['kind']} still expected" for row in rows
                     if row["unreceived_cents"] > 0]
            return "Expected funding", facts or ["No outstanding funding receipts in this year."], "Funding & grants"
        facts = [f"{row['name']} · {money(row['remaining_cents'])} {row['kind']} remaining" for row in rows
                 if row["remaining_cents"] > 0]
        return "Recorded unspent funding", facts or ["No funding source has an unspent recorded balance."], "Funding & grants"
    return "Recorded financial position", [
        f"Confirmed purchases · {ledger['spending']['purchase_count']}",
        f"Cash · {money(totals['cash_cents'])} spent · {money(balances['cash'][scoped_balance])} left",
        f"Purchasing credits · {money(totals['credit_cents'])} spent · {money(balances['credit'][scoped_balance])} left",
    ], "Financial insights"
