"""Tests for the answer cache and the rate limiter."""

from app.api.guards import AnswerCache, RateLimiter, cache_key


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def answer(text="ok"):
    return {"decision": "answer", "message": text}


def test_cache_key_ignores_case_and_extra_spaces():
    assert cache_key("  How MUCH  is the   fee? ") == cache_key("how much is the fee?")


def test_cache_returns_what_was_stored():
    cache = AnswerCache()
    cache.put("How much is the fee?", answer("TK 4,025"))
    assert cache.get("how much is the fee?")["message"] == "TK 4,025"
    assert cache.get("another question") is None


def test_unavailable_results_are_never_cached():
    cache = AnswerCache()
    cache.put("question", {"decision": "unavailable"})
    assert cache.get("question") is None
    assert len(cache) == 0


def test_entries_expire():
    clock = FakeClock()
    cache = AnswerCache(ttl_seconds=60, clock=clock)
    cache.put("question", answer())
    clock.now = 59
    assert cache.get("question") is not None
    clock.now = 61
    assert cache.get("question") is None


def test_the_oldest_entry_is_dropped_when_full():
    cache = AnswerCache(max_items=2)
    cache.put("one", answer("1"))
    cache.put("two", answer("2"))
    cache.get("one")  # "one" was used recently, so "two" is now the oldest
    cache.put("three", answer("3"))
    assert cache.get("two") is None
    assert cache.get("one") is not None
    assert cache.get("three") is not None


def test_limiter_allows_up_to_the_limit_then_blocks():
    clock = FakeClock()
    limiter = RateLimiter(limit=3, window_seconds=60, clock=clock)
    assert [limiter.allow("visitor")[0] for _ in range(3)] == [True, True, True]
    allowed, wait = limiter.allow("visitor")
    assert allowed is False and 1 <= wait <= 60


def test_limiter_allows_again_after_the_window():
    clock = FakeClock()
    limiter = RateLimiter(limit=1, window_seconds=60, clock=clock)
    assert limiter.allow("visitor")[0] is True
    assert limiter.allow("visitor")[0] is False
    clock.now = 61
    assert limiter.allow("visitor")[0] is True


def test_visitors_are_counted_separately():
    limiter = RateLimiter(limit=1, window_seconds=60, clock=FakeClock())
    assert limiter.allow("a")[0] is True
    assert limiter.allow("b")[0] is True
    assert limiter.allow("a")[0] is False


def test_limiter_forgets_old_visitors_when_full():
    limiter = RateLimiter(limit=1, window_seconds=60, clock=FakeClock(), max_visitors=2)
    for visitor in ("a", "b", "c"):
        limiter.allow(visitor)
    assert len(limiter._hits) == 2
