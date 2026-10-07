"""One review plus one correction share the original review deadline and 64k."""

from datetime import datetime, timedelta, timezone

from .store import StudyError

REVIEW_SECONDS = 60
FINISH_SECONDS = 5
REVIEW_CALLS = 2
FINISH_TOKENS = 256


def reservation(row, now=None, *, correction=True, review_seconds=REVIEW_SECONDS):
    now = now or datetime.now(timezone.utc)
    calls = REVIEW_CALLS if correction else 1
    if not 0 < review_seconds <= REVIEW_SECONDS:
        raise StudyError("FINAL_REVIEW_BUDGET_UNAVAILABLE")
    if (
        (row["deadline"] - now).total_seconds() <= review_seconds + FINISH_SECONDS
        or row["model_calls"] + 1 + calls > 6
        or row["reserved_tokens"] + FINISH_TOKENS >= 64000
    ):
        raise StudyError("FINAL_REVIEW_BUDGET_UNAVAILABLE")
    return {
        "review_seconds": review_seconds,
        "finish_seconds": FINISH_SECONDS,
        "model_calls": calls,
        "tokens": 0,
        "version": "dynamic_final_review_v2",
        "estimated": None,
        "safety_margin": 0,
        "finish_tokens": FINISH_TOKENS,
        "preparation_deadline": (
            row["deadline"] - timedelta(seconds=review_seconds + FINISH_SECONDS)
        ).isoformat(),
        "pending": True,
        "correction_pending": correction,
    }


def timeout(row, *, final_review=False, now=None):
    now = now or datetime.now(timezone.utc)
    allocation = row.get("final_review_reservation")
    if not allocation:
        path = row.get("explanation_path_reservation")
        if path:
            remaining = (datetime.fromisoformat(path["preparation_deadline"]) - now).total_seconds()
            if remaining <= 0:
                raise StudyError("FINAL_REVIEW_BUDGET_UNAVAILABLE")
            return remaining
        return max(0.1, (row["deadline"] - now).total_seconds())
    cutoff = (
        row["deadline"] - timedelta(seconds=allocation["finish_seconds"])
        if final_review
        else datetime.fromisoformat(allocation["preparation_deadline"])
    )
    remaining = (cutoff - now).total_seconds()
    if remaining <= 0 or (
        final_review and allocation["pending"] and remaining < allocation["review_seconds"]
    ):
        raise StudyError("FINAL_REVIEW_BUDGET_UNAVAILABLE")
    if final_review:
        # The first request cannot consume the correction's entire time slot.
        # Both still share the original cutoff; recovery never extends it.
        seconds = allocation["review_seconds"]
        if allocation["pending"]:
            calls = (
                allocation["model_calls"]
                if allocation.get("version") == "dynamic_final_review_v2"
                else REVIEW_CALLS
            )
            seconds /= calls
        return min(seconds, remaining)
    return remaining


def margin(cost):
    return min(512, max(128, (cost + 19) // 20))


def priced(allocation, estimate):
    cost = estimate["cost"]
    calls = allocation.get("model_calls", REVIEW_CALLS)
    correction = estimate.get("correction_estimate", {"cost": cost + 1024})["cost"] if calls > 1 else 0
    correction_tokens = correction + margin(correction) if calls > 1 else 0
    return {
        **allocation,
        "estimated": cost,
        "tokens": cost + margin(cost) + correction_tokens,
        "model_calls": calls,
        "correction_pending": allocation.get("correction_pending", calls > 1),
        "correction_estimated": correction,
        "correction_tokens": correction_tokens,
        "version": "dynamic_final_review_v2",
        "finish_tokens": allocation.get("finish_tokens", FINISH_TOKENS),
        "safety_margin": margin(cost) + (margin(correction) if calls > 1 else 0),
        "request_estimate": estimate,
    }


def check_spend(row, kind, tokens, final_review):
    allocation = row.get("final_review_reservation")
    if not allocation:
        return
    if kind == "model" and allocation["pending"] and allocation.get("estimated") is None:
        raise StudyError("FINAL_REVIEW_ESTIMATE_REQUIRED")
    if allocation["pending"]:
        protected = (
            allocation["tokens"]
            if not final_review
            else allocation.get("correction_tokens", 0) + margin(tokens)
        )
        calls = allocation["model_calls"] if not final_review else allocation["model_calls"] - 1
    else:
        protected = (
            allocation.get("correction_tokens", 0)
            if allocation.get("correction_pending") and not final_review
            else 0
        )
        calls = int(bool(allocation.get("correction_pending"))) if not final_review else 0
    if (kind == "model" and row["model_calls"] + 1 + calls > 6) or row[
        "reserved_tokens"
    ] + tokens + protected + allocation.get("finish_tokens", 0) > 64000:
        raise StudyError("FINAL_REVIEW_BUDGET_UNAVAILABLE")
