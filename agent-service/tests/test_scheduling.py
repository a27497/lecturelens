from datetime import datetime, timedelta, timezone

import pytest

from lecturelens_agent.study.scheduling import POLICY, new_state, schedule

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "rating,seconds,stability,state",
    [
        ("Again", 60, 0.212, 1),
        ("Hard", 330, 1.2931, 1),
        ("Good", 600, 2.3065, 1),
        ("Easy", 691200, 8.2956, 2),
    ],
)
def test_new_card_golden(rating, seconds, stability, state):
    initial = new_state(NOW)
    updated = schedule(initial, rating, NOW)
    assert updated["due"] == (NOW + timedelta(seconds=seconds)).isoformat()
    assert updated["stability"] == stability and updated["state"] == state
    assert initial == new_state(NOW)  # Scheduling cannot mutate the logged before-state.
    assert schedule(initial, rating, NOW) == updated


@pytest.mark.parametrize(
    "index,rating,due,stability,state",
    [
        (0, "Good", "2026-01-01T00:10:00+00:00", 2.3065, 1),
        (1, "Good", "2026-01-03T00:10:00+00:00", 2.3065, 2),
        (2, "Again", "2026-01-03T00:20:00+00:00", 0.6077016626638644, 3),
        (3, "Good", "2026-01-04T00:20:00+00:00", 0.6597976257475758, 2),
        (4, "Easy", "2026-01-08T00:20:00+00:00", 4.086147801451196, 2),
    ],
)
def test_learning_lapse_relearning_golden(index, rating, due, stability, state):
    result, now = new_state(NOW), NOW
    for item in ["Good", "Good", "Again", "Good", "Easy"][: index + 1]:
        result = schedule(result, item, now)
        now = datetime.fromisoformat(result["due"])
    assert item == rating
    assert result["due"] == due and result["state"] == state
    assert result["stability"] == pytest.approx(stability)


@pytest.mark.parametrize("offset", [-8, 0, 8])
def test_same_instant_same_result_across_offsets(offset):
    local = NOW.astimezone(timezone(timedelta(hours=offset)))
    assert schedule(new_state(NOW), "Good", local) == schedule(new_state(NOW), "Good", NOW)


def test_naive_and_backwards_times_rejected():
    with pytest.raises(ValueError, match="aware"):
        schedule(new_state(NOW), "Good", NOW.replace(tzinfo=None))
    prior = schedule(new_state(NOW), "Good", NOW)
    with pytest.raises(ValueError, match="precede"):
        schedule(prior, "Good", NOW - timedelta(seconds=1))


def test_policy_pins_defaults_and_disables_fuzzing():
    assert POLICY["implementation"] == "fsrs==6.3.0"
    assert len(POLICY["parameters"]) == 21 and POLICY["desired_retention"] == 0.9
    assert POLICY["enable_fuzzing"] is False and POLICY["maximum_interval"] == 36500
