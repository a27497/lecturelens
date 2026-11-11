"""FSRS-6 via MIT py-fsrs 6.3.0; UTC instants, no random interval fuzzing."""

from datetime import datetime, timezone

from fsrs import Card, Rating, Scheduler

SCHEDULER = Scheduler(desired_retention=0.9, enable_fuzzing=False)
POLICY = {"implementation": "fsrs==6.3.0", **SCHEDULER.to_dict()}
RATINGS = {"Again": Rating.Again, "Hard": Rating.Hard, "Good": Rating.Good, "Easy": Rating.Easy}


def new_state(now):
    return Card(card_id=0, due=now).to_dict()


def schedule(state, rating, now):
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("An aware review time is required")
    now = now.astimezone(timezone.utc)
    card = Card.from_dict(state)
    if card.last_review and now < card.last_review:
        raise ValueError("Review time cannot precede the last review")
    updated, _ = SCHEDULER.review_card(card, RATINGS[rating], review_datetime=now)
    return updated.to_dict()


def utc_now():
    return datetime.now(timezone.utc)
