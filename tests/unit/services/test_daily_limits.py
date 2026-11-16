from datetime import UTC, datetime, timedelta

import pytest

from nisar_hazard_watch.adapters.db.job_repository import SqlJobRepository
from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.headers import RETRY_AFTER_HEADER
from nisar_hazard_watch.exceptions.exploration_errors import DailyLimitReachedError
from nisar_hazard_watch.services.daily_limits import DailyLimits
from nisar_hazard_watch.utils.client_hash import hash_client_key
from tests.factories import make_job
from tests.unit.services.conftest import START, ManualClock

CLIENT = "203.0.113.7"
OTHER_CLIENT = "203.0.113.8"
APP_LIMIT = 10
CLIENT_LIMIT = 5
SMALL_LIMIT = 2
NEXT_MIDNIGHT = datetime(2026, 11, 13, 0, 0, tzinfo=UTC)
SECONDS_TO_MIDNIGHT = 12 * 3600


async def _add(repository: SqlJobRepository, index: int, **overrides: object) -> None:
    values: dict[str, object] = {
        "id": f"exp_{index:016x}",
        "runner_id": f"run-{index}",
        "client_key": hash_client_key(client=CLIENT),
        "created_at": START,
        **overrides,
    }
    await repository.add(job=make_job(**values))


def _limits(
    repository: SqlJobRepository,
    clock: ManualClock,
    app_limit: int = APP_LIMIT,
    client_limit: int = CLIENT_LIMIT,
) -> DailyLimits:
    return DailyLimits(
        repository=repository, app_limit=app_limit, client_limit=client_limit, clock=clock
    )


async def test_the_allowance_counts_only_todays_submitted_runs_that_spend_it(
    repository: SqlJobRepository, clock: ManualClock
) -> None:
    # Arrange
    await _add(repository=repository, index=1)
    await _add(repository=repository, index=2)
    await _add(repository=repository, index=3, client_key=hash_client_key(client=OTHER_CLIENT))
    await _add(repository=repository, index=4, created_at=START - timedelta(days=1))
    await _add(repository=repository, index=5, runner_id=None)
    await _add(repository=repository, index=6, counts_toward_limits=False)
    limits = _limits(repository=repository, clock=clock)

    # Act
    view = await limits.view(client=CLIENT)

    # Assert
    assert view.remaining_app == APP_LIMIT - 3
    assert view.remaining_client == CLIENT_LIMIT - 2
    assert (view.limit_app, view.limit_client) == (APP_LIMIT, CLIENT_LIMIT)


async def test_the_allowance_resets_at_the_next_utc_midnight(
    repository: SqlJobRepository, clock: ManualClock
) -> None:
    # Arrange
    limits = _limits(repository=repository, clock=clock)

    # Act
    view = await limits.view(client=CLIENT)

    # Assert
    assert view.resets_at == NEXT_MIDNIGHT


async def test_a_client_over_its_limit_is_refused_with_the_time_left_until_the_reset(
    repository: SqlJobRepository, clock: ManualClock
) -> None:
    # Arrange
    await _add(repository=repository, index=1)
    await _add(repository=repository, index=2)
    limits = _limits(repository=repository, clock=clock, client_limit=SMALL_LIMIT)

    # Act / Assert
    with pytest.raises(DailyLimitReachedError) as refused:
        await limits.require(client=CLIENT)
    assert refused.value.reason_code is ReasonCode.DAILY_LIMIT_REACHED
    assert refused.value.status_code == 429
    assert refused.value.headers[RETRY_AFTER_HEADER] == str(SECONDS_TO_MIDNIGHT)


async def test_the_whole_app_over_its_limit_refuses_every_client(
    repository: SqlJobRepository, clock: ManualClock
) -> None:
    # Arrange
    await _add(repository=repository, index=1, client_key=hash_client_key(client=OTHER_CLIENT))
    await _add(repository=repository, index=2, client_key=hash_client_key(client=OTHER_CLIENT))
    limits = _limits(repository=repository, clock=clock, app_limit=SMALL_LIMIT)

    # Act / Assert
    with pytest.raises(DailyLimitReachedError) as refused:
        await limits.require(client=CLIENT)
    assert "app" in refused.value.detail


async def test_a_run_without_a_known_client_is_checked_against_the_app_limit_only(
    repository: SqlJobRepository, clock: ManualClock
) -> None:
    # Arrange
    await _add(repository=repository, index=1)
    await _add(repository=repository, index=2)
    limits = _limits(repository=repository, clock=clock, client_limit=1)

    # Act
    view = await limits.view(client=None)
    await limits.require(client=None)

    # Assert
    assert view.remaining_client == 1
    assert view.remaining_app == APP_LIMIT - 2


async def test_a_client_with_allowance_left_is_let_through(
    repository: SqlJobRepository, clock: ManualClock
) -> None:
    # Arrange
    await _add(repository=repository, index=1)
    limits = _limits(repository=repository, clock=clock)

    # Act
    await limits.require(client=CLIENT)

    # Assert
    assert (await limits.view(client=CLIENT)).remaining_client == CLIENT_LIMIT - 1
