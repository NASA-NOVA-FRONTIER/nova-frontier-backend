from nisar_hazard_watch.utils.rate_limiter import RateLimiter

MAX_REQUESTS = 3
WINDOW_SECONDS = 60.0


class ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_requests_beyond_the_limit_are_refused_until_the_window_slides() -> None:
    # Arrange
    clock = ManualClock()
    limiter = RateLimiter(max_requests=MAX_REQUESTS, window_seconds=WINDOW_SECONDS, clock=clock)

    # Act
    first_window = [limiter.allow(key="client") for _ in range(MAX_REQUESTS + 1)]
    clock.now = WINDOW_SECONDS
    after_window = limiter.allow(key="client")

    # Assert
    assert first_window == [True] * MAX_REQUESTS + [False]
    assert after_window is True


def test_each_client_has_its_own_budget() -> None:
    # Arrange
    limiter = RateLimiter(max_requests=1, window_seconds=WINDOW_SECONDS, clock=ManualClock())

    # Act
    first = limiter.allow(key="a")
    second = limiter.allow(key="b")
    repeat = limiter.allow(key="a")

    # Assert
    assert (first, second, repeat) == (True, True, False)


def test_a_limited_client_learns_how_long_until_a_slot_frees_up() -> None:
    # Arrange
    clock = ManualClock()
    limiter = RateLimiter(max_requests=1, window_seconds=WINDOW_SECONDS, clock=clock)
    limiter.allow(key="client")
    clock.now = 20.0

    # Act
    wait = limiter.retry_after(key="client")

    # Assert
    assert wait == WINDOW_SECONDS - 20.0


def test_a_client_within_its_budget_has_nothing_to_wait_for() -> None:
    # Arrange
    limiter = RateLimiter(
        max_requests=MAX_REQUESTS, window_seconds=WINDOW_SECONDS, clock=ManualClock()
    )
    limiter.allow(key="client")

    # Act
    wait = limiter.retry_after(key="client")
    unknown = limiter.retry_after(key="nobody")

    # Assert
    assert wait == 0.0
    assert unknown == 0.0
