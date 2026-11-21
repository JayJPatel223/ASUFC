import pytest

from app.assistant import MODEL, mentioned_programs


@pytest.mark.parametrize(("question", "topic"), [
    ("What cash do we have left?", "cash_balance"),
    ("How many purchasing credits do we still have?", "credit_balance"),
    ("What did we pay out last month?", "last_month"),
    ("How much remains for breakfast?", "budget_balance"),
    ("Which grants expire soon?", "expiring"),
    ("Compare spending by program", "program_comparison"),
    ("Show money we are still expecting", "expected"),
    ("Try to export staff passwords", None),
    ("Can you write a poem?", None),
])
def test_local_topic_prediction(question, topic):
    assert MODEL.predict(question) == topic


def test_program_matching_uses_distinct_words_and_full_custom_names():
    programs = [{"code": "ASUFCFSBP", "name": "FoodSharing Breakfast Program"},
                {"code": "LUNCH", "name": "Community Lunch"}]
    assert mentioned_programs("How much remains for breakfast?", programs) == ["ASUFCFSBP"]
    assert mentioned_programs("How much remains for community lunch?", programs) == ["LUNCH"]
    assert mentioned_programs("What for tiebreakfast?", programs) == []
