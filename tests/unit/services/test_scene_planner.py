import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest

from nisar_hazard_watch.adapters.asf.asf_catalog import AsfCatalog
from nisar_hazard_watch.constants.sar import MIN_IMAGES, WINDOW_DAYS, Direction, PlanStatus
from nisar_hazard_watch.exceptions.catalog_errors import CatalogUnavailableError
from nisar_hazard_watch.models.geometry import Aoi
from nisar_hazard_watch.models.scene import Scene, ScenePlan
from nisar_hazard_watch.services.scene_planner import ScenePlanner
from tests.factories import REVISIT_DAYS, SERIES_START, make_scene, make_series, qadirabad_aoi

FIXTURE = Path(__file__).parents[2] / "fixtures" / "asf_qadirabad.json"
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
MAX_IMAGES = 5


class FakeCatalog:
    def __init__(self, scenes: list[Scene]) -> None:
        self._scenes = scenes
        self.calls: list[tuple[Aoi, datetime, datetime]] = []

    async def search(self, aoi: Aoi, start: datetime, end: datetime) -> list[Scene]:
        self.calls.append((aoi, start, end))
        return self._scenes


class BrokenCatalog:
    async def search(self, aoi: Aoi, start: datetime, end: datetime) -> list[Scene]:
        raise CatalogUnavailableError("down")


def _planner(catalog: object) -> ScenePlanner:
    return ScenePlanner(catalog=catalog, clock=lambda: NOW)  # type: ignore[arg-type]


async def test_qadirabad_is_planned_from_the_real_catalog_into_one_group_of_five_dates() -> None:
    # Arrange
    body = json.loads(FIXTURE.read_text())
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code=200, json=body))

    # Act
    async with httpx.AsyncClient(transport=transport) as client:
        plan = await _planner(catalog=AsfCatalog(client=client)).plan(aoi=qadirabad_aoi())

    # Assert
    dates = [scene.acquired_at for scene in plan.scenes]
    assert plan.status is PlanStatus.READY
    assert plan.group is not None
    assert plan.group.series_key == "084_A_018_4005_DHDH"
    assert len(plan.scenes) == MAX_IMAGES
    assert dates == sorted(dates)
    assert dates[-1].date().isoformat() == "2026-11-11"
    assert all(scene.track == 84 and scene.frame == 18 for scene in plan.scenes)
    assert plan.maturity_mixed is True
    assert len({scene.acquired_at for scene in plan.scenes}) == len(plan.scenes)


async def test_the_window_is_the_last_five_months_ending_now() -> None:
    # Arrange
    catalog = FakeCatalog(scenes=make_series(count=12))

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    _, start, end = catalog.calls[0]
    assert end == NOW
    assert start == NOW - timedelta(days=WINDOW_DAYS)
    assert (plan.window_start, plan.window_end) == (start, end)


async def test_a_clean_series_is_ready_and_not_flagged_as_mixed() -> None:
    # Arrange
    catalog = FakeCatalog(scenes=make_series(count=12))

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    assert plan.status is PlanStatus.READY
    assert plan.maturity_mixed is False
    assert plan.notes == []


async def test_fewer_than_four_usable_dates_is_an_insufficient_history_plan_not_an_error() -> None:
    # Arrange
    newest = make_series(count=1)[0].acquired_at
    scenes = [make_scene(acquired_at=newest - timedelta(days=30 * step)) for step in range(3)]
    catalog = FakeCatalog(scenes=scenes)

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    assert plan.status is PlanStatus.INSUFFICIENT_HISTORY
    assert len(plan.scenes) == 3
    assert any("3 usable" in note for note in plan.notes)


async def test_an_empty_catalog_is_a_no_coverage_plan() -> None:
    # Arrange
    catalog = FakeCatalog(scenes=[])

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    assert plan.status is PlanStatus.NO_COVERAGE
    assert plan.scenes == []
    assert plan.group is None


async def test_a_group_that_only_partly_covers_the_aoi_is_planned_with_a_note() -> None:
    # Arrange
    catalog = FakeCatalog(scenes=make_series(count=12, coverage=0.6))

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    assert plan.status is PlanStatus.READY
    assert any("60%" in note for note in plan.notes)


async def test_duplicate_acquisitions_never_reach_the_plan() -> None:
    # Arrange
    series = make_series(count=12)
    duplicates = [make_scene(acquired_at=series[-1].acquired_at, crid="P00001")]
    catalog = FakeCatalog(scenes=[*series, *duplicates])

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    times = [scene.acquired_at for scene in plan.scenes]
    assert len(times) == len(set(times))


async def test_catalog_failures_propagate_as_their_own_error() -> None:
    # Arrange
    planner = _planner(catalog=BrokenCatalog())

    # Act / Assert
    with pytest.raises(expected_exception=CatalogUnavailableError):
        await planner.plan(aoi=qadirabad_aoi())


RANGE_START = SERIES_START.date()
RANGE_END = RANGE_START + timedelta(days=REVISIT_DAYS * 11)
DATE_RANGE = (RANGE_START, RANGE_END)


async def test_a_range_reads_its_whole_days_and_spreads_five_passes_across_it() -> None:
    # Arrange
    series = make_series(count=12)
    catalog = FakeCatalog(scenes=series)

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi(), date_range=DATE_RANGE)

    # Assert
    _, start, end = catalog.calls[0]
    assert (start, end) == (
        datetime(2026, 6, 12, tzinfo=UTC),
        datetime(2026, 10, 22, 23, 59, 59, tzinfo=UTC),
    )
    assert (plan.window_start.date(), plan.window_end.date()) == DATE_RANGE
    assert plan.status is PlanStatus.READY
    offsets = [(scene.acquired_at - SERIES_START).days for scene in plan.scenes]
    # Whole days: targets every 33 d 6 h from 12 Jun 00:00, against passes at 02:00.
    assert offsets == [0, 36, 72, 96, 132]
    assert [item.granule_id for item in plan.passes] == [scene.granule_id for scene in series]


@pytest.mark.parametrize(
    ("count", "status", "picked"),
    [
        pytest.param(4, PlanStatus.READY, 4, id="four-is-ready"),
        pytest.param(3, PlanStatus.INSUFFICIENT_HISTORY, 3, id="three-is-not-enough"),
        pytest.param(0, PlanStatus.NO_COVERAGE, 0, id="none-is-no-coverage"),
    ],
)
async def test_a_range_keeps_todays_thresholds(count: int, status: PlanStatus, picked: int) -> None:
    # Arrange
    catalog = FakeCatalog(scenes=make_series(count=count))

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi(), date_range=DATE_RANGE)

    # Assert
    assert plan.status is status
    assert len(plan.scenes) == picked


async def test_a_range_tops_up_from_its_own_passes_when_targets_share_them() -> None:
    # Arrange
    # Four passes in the first 36 days of a 132-day range: three targets fall on the last one.
    clustered = make_series(count=4)
    catalog = FakeCatalog(scenes=clustered)

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi(), date_range=DATE_RANGE)

    # Assert
    assert plan.status is PlanStatus.READY
    assert len(plan.scenes) == MIN_IMAGES
    assert {scene.granule_id for scene in plan.scenes} <= {s.granule_id for s in clustered}


async def test_the_default_window_also_lists_every_pass_of_its_series() -> None:
    # Arrange
    series = make_series(count=12)
    catalog = FakeCatalog(scenes=series)

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    assert [item.acquired_at for item in plan.passes] == [s.acquired_at for s in series]
    assert plan.window_end == NOW
    assert plan.window_start == NOW - timedelta(days=WINDOW_DAYS)


async def _real_plan(
    direction: Direction | None = None, series_key: str | None = None
) -> ScenePlan:
    body = json.loads(FIXTURE.read_text())
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code=200, json=body))
    async with httpx.AsyncClient(transport=transport) as client:
        planner = _planner(catalog=AsfCatalog(client=client))
        return await planner.plan(aoi=qadirabad_aoi(), direction=direction, series_key=series_key)


async def test_qadirabad_lists_every_series_found_with_the_default_first() -> None:
    # Act
    plan = await _real_plan()

    # Assert
    keys = [option.series_key for option in plan.series]
    assert plan.group is not None
    assert keys[0] == plan.group.series_key == "084_A_018_4005_DHDH"
    assert len(keys) == 7
    assert {option.direction for option in plan.series} == {
        Direction.ASCENDING,
        Direction.DESCENDING,
    }


async def test_qadirabad_descending_plans_the_best_descending_series() -> None:
    # Act
    plan = await _real_plan(direction=Direction.DESCENDING)

    # Assert
    assert plan.status is PlanStatus.READY
    assert plan.group is not None
    assert plan.group.series_key == "063_D_072_4005_DHDH"
    assert [s.acquired_at.date().isoformat() for s in plan.scenes] == [
        "2026-06-30",
        "2026-07-24",
        "2026-10-04",
        "2026-10-28",
    ]
    assert all(scene.direction is Direction.DESCENDING for scene in plan.scenes)


async def test_qadirabad_plans_exactly_the_series_key_asked_for() -> None:
    # Act
    plan = await _real_plan(series_key="135_D_072_2005_QPDH")

    # Assert
    assert plan.group is not None
    assert plan.group.series_key == "135_D_072_2005_QPDH"
    assert {scene.mode for scene in plan.scenes} == {"QPDH"}


async def test_a_series_not_found_is_no_coverage_that_still_lists_what_was_found() -> None:
    # Act
    plan = await _real_plan(series_key="999_D_001_4005_DHDH")

    # Assert
    assert plan.status is PlanStatus.NO_COVERAGE
    assert plan.scenes == []
    assert len(plan.series) == 7
    assert plan.notes[0].startswith(
        "no NISAR L-band GCOV series 999_D_001_4005_DHDH covers this area"
    )


async def test_series_with_equal_scores_are_listed_smallest_key_first_as_chosen() -> None:
    # Arrange: two full, dual-pol series with the same dates.
    descending = make_series(count=6, track=63, direction=Direction.DESCENDING, frame=72)
    ascending = make_series(count=6)
    catalog = FakeCatalog(scenes=[*descending, *ascending])

    # Act
    plan = await _planner(catalog=catalog).plan(aoi=qadirabad_aoi())

    # Assert
    keys = [option.series_key for option in plan.series]
    assert keys == ["063_D_072_4005_DHDH", "084_A_018_4005_DHDH"]
    assert plan.group is not None
    assert plan.group.series_key == keys[0]
