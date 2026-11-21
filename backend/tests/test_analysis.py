from datetime import date

from app.analysis import forecast


def test_estimate_uses_only_six_complete_months():
    months = [{"label": f"2026-{month:02}", "cash_cents": month * 100, "credit_cents": 75}
              for month in range(4, 11)]
    forecasted = forecast(months, date(2026, 10, 16), date(2026, 4, 1), date(2027, 3, 31))
    assert forecasted["estimate"] == {"label": "2026-11", "cash_cents": 650, "credit_cents": 75}
    assert forecasted["months"] == [f"2026-{month:02}" for month in range(4, 10)]
    assert forecast(months[1:], date(2026, 10, 16), date(2026, 4, 1), date(2027, 3, 31))["estimate"] is None


def test_estimate_requires_configured_dates_and_future_month_within_year():
    today = date(2026, 12, 12)
    assert forecast([], today, None, None)["estimate"] is None
    assert forecast([], today, date(2026, 1, 1), date(2026, 12, 31))["estimate"] is None
