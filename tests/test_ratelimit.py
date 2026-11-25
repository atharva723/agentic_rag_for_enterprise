"""The rate limiter: sliding windows per person, kept in memory. A clock the tests can move (see conftest.py) stands in for time."""
import threading

import pytest

from app import ratelimit
from app.ratelimit import RateLimiter, Refused, wait_text

MINUTE, DAY = 60, 86_400


@pytest.fixture
def limiter(clock):
    return RateLimiter(clock)


def test_uses_up_to_the_limit_are_allowed_and_the_next_one_is_refused_with_how_long_to_wait(limiter, clock):
    assert [limiter.take("ana", {MINUTE: 3}) for _ in range(3)] == [None, None, None]
    clock.now += 10
    assert limiter.take("ana", {MINUTE: 3}) == Refused(wait=50, window=MINUTE, most=3)  # the first use leaves the window 60 seconds after it


def test_the_window_slides_so_waiting_is_enough(limiter, clock):
    for second in (0, 20, 40):  # three uses, spread over the minute
        clock.now = 1000 + second
        assert limiter.take("ana", {MINUTE: 3}) is None
    clock.now = 1059
    assert limiter.take("ana", {MINUTE: 3}).wait == 1  # the first one leaves in a second...
    clock.now = 1060
    assert limiter.take("ana", {MINUTE: 3}) is None  # ...and then exactly one more is allowed
    assert limiter.take("ana", {MINUTE: 3}).wait == 20  # the next use to leave is the one made 20 seconds into the minute


def test_a_refused_use_is_not_counted(limiter, clock):
    limiter.take("ana", {MINUTE: 1})
    clock.now += 30
    for _ in range(5):  # hammering does not make the wait longer: it is always 30 seconds until the first use leaves
        assert limiter.take("ana", {MINUTE: 1}).wait == 30
    clock.now += 30
    assert limiter.take("ana", {MINUTE: 1}) is None


def test_everyone_has_their_own_count(limiter):
    assert limiter.take("ana", {MINUTE: 1}) is None
    assert limiter.take("ana", {MINUTE: 1}) is not None
    assert limiter.take("ben", {MINUTE: 1}) is None


def test_with_two_limits_the_one_that_makes_you_wait_longest_is_reported(limiter, clock):
    limits = {MINUTE: 5, DAY: 2}
    assert limiter.take("ana", limits) is None
    clock.now += 5
    assert limiter.take("ana", limits) is None
    clock.now += 5
    assert limiter.take("ana", limits) == Refused(wait=DAY - 10, window=DAY, most=2)  # 2 a day is used up, long before 5 a minute is
    clock.now += DAY - 10
    assert limiter.take("ana", limits) is None  # the first use has left the day window


def test_the_minute_limit_alone_can_refuse_while_the_day_has_room(limiter):
    limits = {MINUTE: 2, DAY: 50}
    limiter.take("ana", limits)
    limiter.take("ana", limits)
    assert limiter.take("ana", limits) == Refused(wait=60, window=MINUTE, most=2)


@pytest.mark.parametrize("limits", [{}, {MINUTE: 0}, {MINUTE: 0, DAY: 0}, {MINUTE: -1}], ids=["none", "zero", "all zero", "negative"])
def test_a_limit_of_zero_means_no_limit_and_nothing_is_remembered(limiter, limits):
    assert all(limiter.take("ana", limits) is None for _ in range(100))
    assert limiter.uses == {}


def test_a_window_set_to_zero_is_skipped_while_the_other_one_still_counts(limiter):
    limits = {MINUTE: 0, DAY: 2}
    assert [limiter.take("ana", limits) for _ in range(2)] == [None, None]
    assert limiter.take("ana", limits).window == DAY


def test_giving_a_use_back_frees_it(limiter):
    limiter.take("ana", {MINUTE: 1})
    limiter.give_back("ana")
    assert limiter.take("ana", {MINUTE: 1}) is None
    limiter.give_back("nobody")  # harmless for someone who has no uses
    limiter.give_back("ana")
    limiter.give_back("ana")
    assert limiter.take("ana", {MINUTE: 1}) is None


def test_people_who_have_not_been_seen_for_a_whole_window_are_forgotten_so_the_table_cannot_grow_forever(limiter, clock, monkeypatch):
    monkeypatch.setattr(ratelimit, "SWEEP_AT", 50)
    for n in range(60):
        limiter.take(f"user-{n}", {MINUTE: 1})
    clock.now += MINUTE
    limiter.take("latecomer", {MINUTE: 1})
    assert list(limiter.uses) == ["latecomer"]


def test_many_threads_at_once_cannot_get_past_the_limit(limiter):
    allowed = []

    def ask():
        if limiter.take("ana", {MINUTE: 5}) is None:
            allowed.append(1)

    threads = [threading.Thread(target=ask) for _ in range(40)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(allowed) == 5


def test_reset_forgets_everyone(limiter):
    limiter.take("ana", {MINUTE: 1})
    limiter.reset()
    assert limiter.take("ana", {MINUTE: 1}) is None


@pytest.mark.parametrize(
    "seconds, text",
    [(1, "1 second"), (12, "12 seconds"), (59, "59 seconds"), (60, "1 minute"), (61, "2 minutes"), (3599, "1 hour"), (3600, "1 hour"), (7300, "3 hours"), (86_400, "24 hours")],
)
def test_waits_are_written_in_plain_words_and_rounded_up(seconds, text):
    assert wait_text(seconds) == text
