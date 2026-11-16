from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from nisar_hazard_watch.adapters.db.job_repository import SqlJobRepository
from nisar_hazard_watch.adapters.db.models import Base
from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.explorations import ExplorationStatus, Lens, Stage
from nisar_hazard_watch.models.exploration import ProblemInfo
from tests.factories import make_job

NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
CACHE_KEY = "b" * 64
TIMEOUT_ERROR = ProblemInfo(reason_code=ReasonCode.TIMEOUT_PARTIAL, detail="late")
ACTIVE_JOBS = 2


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    database = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")
    async with database.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield database
    await database.dispose()


@pytest.fixture
def repository(engine: AsyncEngine) -> SqlJobRepository:
    return SqlJobRepository(session_factory=async_sessionmaker(engine, expire_on_commit=False))


async def test_a_job_survives_a_round_trip_with_its_plan_and_timestamps(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    job = make_job()

    # Act
    await repository.add(job=job)
    loaded = await repository.get(job_id=job.id)

    # Assert
    assert loaded == job
    assert loaded is not None
    assert loaded.created_at.tzinfo is not None


async def test_an_unknown_job_is_none(repository: SqlJobRepository) -> None:
    # Arrange
    unknown_id = "exp_missing"

    # Act
    loaded = await repository.get(job_id=unknown_id)

    # Assert
    assert loaded is None


async def test_a_transition_replaces_the_state_of_an_active_job(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    job = make_job()
    await repository.add(job=job)
    failed = job.model_copy(
        update={
            "status": ExplorationStatus.FAILED,
            "stage": Stage.DONE,
            "error": ProblemInfo(reason_code=ReasonCode.ANALYSIS_FAILED, detail="boom"),
            "finished_at": NOW,
        }
    )

    # Act
    saved = await repository.transition(job=failed)
    loaded = await repository.get(job_id=job.id)

    # Assert
    assert saved is True
    assert loaded is not None
    assert loaded.status is ExplorationStatus.FAILED
    assert loaded.error is not None
    assert loaded.error.reason_code is ReasonCode.ANALYSIS_FAILED


async def test_a_transition_never_overwrites_a_finished_job(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    job = make_job()
    await repository.add(job=job)
    cancelled = job.model_copy(
        update={"status": ExplorationStatus.CANCELLED, "stage": Stage.DONE, "finished_at": NOW}
    )
    succeeded = job.model_copy(
        update={"status": ExplorationStatus.SUCCEEDED, "stage": Stage.DONE, "finished_at": NOW}
    )
    await repository.transition(job=cancelled)

    # Act
    saved = await repository.transition(job=succeeded)
    loaded = await repository.get(job_id=job.id)

    # Assert
    assert saved is False
    assert loaded is not None
    assert loaded.status is ExplorationStatus.CANCELLED


async def test_only_queued_and_running_jobs_count_as_active(repository: SqlJobRepository) -> None:
    # Arrange
    statuses = [
        ExplorationStatus.QUEUED,
        ExplorationStatus.RUNNING,
        ExplorationStatus.SUCCEEDED,
        ExplorationStatus.FAILED,
        ExplorationStatus.CANCELLED,
    ]
    for index, status in enumerate(statuses):
        await repository.add(job=make_job(id=f"exp_{index:016d}", status=status))

    # Act
    active = await repository.count_active(now=NOW)

    # Assert
    assert active == ACTIVE_JOBS


async def test_overdue_jobs_do_not_count_as_active(repository: SqlJobRepository) -> None:
    # Arrange
    await repository.add(job=make_job(id="exp_alive", deadline_at=NOW + timedelta(seconds=5)))
    await repository.add(job=make_job(id="exp_late", deadline_at=NOW - timedelta(seconds=5)))

    # Act
    active = await repository.count_active(now=NOW)

    # Assert
    assert active == 1


async def test_only_earlier_queued_jobs_inside_their_deadline_are_ahead_in_line(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    jobs = [
        make_job(id="exp_earlier", created_at=NOW - timedelta(seconds=20)),
        make_job(
            id="exp_running",
            created_at=NOW - timedelta(seconds=10),
            status=ExplorationStatus.RUNNING,
        ),
        make_job(
            id="exp_late",
            created_at=NOW - timedelta(seconds=5),
            deadline_at=NOW - timedelta(seconds=1),
        ),
        make_job(id="exp_later", created_at=NOW + timedelta(seconds=5)),
    ]
    for job in jobs:
        await repository.add(job=job)

    # Act
    ahead = await repository.count_queued_ahead(
        job=make_job(id="exp_mine", created_at=NOW), now=NOW
    )

    # Assert
    assert ahead == 1


async def test_jobs_created_at_the_same_instant_queue_by_id(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    first = make_job(id="exp_a", created_at=NOW)
    second = make_job(id="exp_b", created_at=NOW)
    for job in (first, second):
        await repository.add(job=job)

    # Act
    ahead_of_first = await repository.count_queued_ahead(job=first, now=NOW)
    ahead_of_second = await repository.count_queued_ahead(job=second, now=NOW)

    # Assert
    assert (ahead_of_first, ahead_of_second) == (0, 1)


async def test_expiring_overdue_jobs_marks_only_those_as_partial(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    await repository.add(job=make_job(id="exp_alive", deadline_at=NOW + timedelta(seconds=5)))
    await repository.add(job=make_job(id="exp_late", deadline_at=NOW - timedelta(seconds=5)))
    await repository.add(
        job=make_job(
            id="exp_done",
            status=ExplorationStatus.SUCCEEDED,
            deadline_at=NOW - timedelta(seconds=5),
        )
    )

    # Act
    expired = await repository.expire_overdue(now=NOW, error=TIMEOUT_ERROR)
    late = await repository.get(job_id="exp_late")
    alive = await repository.get(job_id="exp_alive")
    done = await repository.get(job_id="exp_done")

    # Assert
    assert expired == 1
    assert late is not None
    assert late.status is ExplorationStatus.PARTIAL
    assert late.stage is Stage.DONE
    assert late.finished_at == NOW
    assert late.error == TIMEOUT_ERROR
    assert alive is not None
    assert alive.status is ExplorationStatus.QUEUED
    assert done is not None
    assert done.status is ExplorationStatus.SUCCEEDED


async def test_find_fresh_returns_the_newest_succeeded_job_of_that_key(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    old = make_job(
        id="exp_old",
        status=ExplorationStatus.SUCCEEDED,
        cache_key=CACHE_KEY,
        finished_at=NOW - timedelta(days=2),
    )
    newer = make_job(
        id="exp_new",
        status=ExplorationStatus.SUCCEEDED,
        cache_key=CACHE_KEY,
        finished_at=NOW - timedelta(hours=1),
    )
    failed = make_job(
        id="exp_failed",
        status=ExplorationStatus.FAILED,
        cache_key=CACHE_KEY,
        finished_at=NOW - timedelta(minutes=5),
    )
    other = make_job(
        id="exp_other",
        status=ExplorationStatus.SUCCEEDED,
        cache_key="c" * 64,
        finished_at=NOW - timedelta(minutes=5),
    )
    for job in (old, newer, failed, other):
        await repository.add(job=job)

    # Act
    found = await repository.find_fresh(cache_key=CACHE_KEY, newer_than=NOW - timedelta(days=1))

    # Assert
    assert found is not None
    assert found.id == "exp_new"


async def test_find_fresh_ignores_results_older_than_the_window(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    await repository.add(
        job=make_job(
            status=ExplorationStatus.SUCCEEDED,
            cache_key=CACHE_KEY,
            finished_at=NOW - timedelta(days=3),
        )
    )

    # Act
    found = await repository.find_fresh(cache_key=CACHE_KEY, newer_than=NOW - timedelta(days=1))

    # Assert
    assert found is None


async def test_recent_totals_are_the_seconds_of_comparable_succeeded_runs(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    created = NOW - timedelta(hours=1)
    comparable = [
        make_job(
            id=f"exp_c{index}",
            status=ExplorationStatus.SUCCEEDED,
            created_at=created,
            finished_at=created + timedelta(seconds=seconds),
            deadline_at=created + timedelta(seconds=55),
        )
        for index, seconds in enumerate([30, 40, 50])
    ]
    different_lens = make_job(
        id="exp_lens",
        lens=Lens.WILDFIRE,
        status=ExplorationStatus.SUCCEEDED,
        created_at=created,
        finished_at=created + timedelta(seconds=5),
    )
    for job in (*comparable, different_lens):
        await repository.add(job=job)

    # Act
    totals = await repository.recent_totals(
        lens=Lens.FLOOD_WETLAND, scenes_total=5, area_bucket="<=200", limit=2
    )

    # Assert
    assert len(totals) == 2
    assert sorted(totals) == [30.0, 40.0] or sorted(totals) == [40.0, 50.0]
    assert 5.0 not in totals


async def test_new_runs_are_counted_since_a_moment_for_everyone_or_for_one_client(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    midnight = NOW.replace(hour=0, minute=0)
    await repository.add(job=make_job(id="exp_1", runner_id="r1", client_key="a", created_at=NOW))
    await repository.add(job=make_job(id="exp_2", runner_id="r2", client_key="a", created_at=NOW))
    await repository.add(job=make_job(id="exp_3", runner_id="r3", client_key="b", created_at=NOW))
    await repository.add(
        job=make_job(
            id="exp_4", runner_id="r4", client_key="a", created_at=midnight - timedelta(seconds=1)
        )
    )

    # Act
    everyone = await repository.count_new_since(since=midnight)
    only_a = await repository.count_new_since(since=midnight, client_key="a")

    # Assert
    assert everyone == 3
    assert only_a == 2


async def test_runs_that_never_reached_the_runner_or_came_from_its_cache_are_not_counted(
    repository: SqlJobRepository,
) -> None:
    # Arrange
    midnight = NOW.replace(hour=0, minute=0)
    await repository.add(job=make_job(id="exp_1", runner_id=None, created_at=NOW))
    await repository.add(
        job=make_job(id="exp_2", runner_id="r2", counts_toward_limits=False, created_at=NOW)
    )
    await repository.add(job=make_job(id="exp_3", runner_id="r3", created_at=NOW))

    # Act
    counted = await repository.count_new_since(since=midnight)

    # Assert
    assert counted == 1
