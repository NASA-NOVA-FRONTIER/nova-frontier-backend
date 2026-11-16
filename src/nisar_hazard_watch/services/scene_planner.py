from collections.abc import Callable
from datetime import UTC, datetime, time, timedelta
from statistics import mean

from nisar_hazard_watch.constants.sar import (
    END_OF_DAY,
    FULL_COVERAGE,
    MAX_IMAGES,
    MIN_IMAGES,
    SPACING_DAYS,
    SPACING_TOLERANCE_DAYS,
    WINDOW_DAYS,
    PlanStatus,
)
from nisar_hazard_watch.models.geometry import Aoi
from nisar_hazard_watch.models.scene import Scene, ScenePass, ScenePlan
from nisar_hazard_watch.ports.sar_catalog import SarCatalog
from nisar_hazard_watch.services.scene_selection import (
    choose_group,
    dedupe_scenes,
    select_dates,
    select_spread,
)
from nisar_hazard_watch.utils.date_range import DateRange


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ScenePlanner:
    """From an area and "now" to the exact scenes to read: one group, up to five dates."""

    def __init__(
        self,
        catalog: SarCatalog,
        clock: Callable[[], datetime] = _utc_now,
        window_days: int = WINDOW_DAYS,
        max_images: int = MAX_IMAGES,
        min_images: int = MIN_IMAGES,
        spacing_days: int = SPACING_DAYS,
        tolerance_days: int = SPACING_TOLERANCE_DAYS,
    ) -> None:
        self._catalog = catalog
        self._clock = clock
        self._window_days = window_days
        self._max_images = max_images
        self._min_images = min_images
        self._spacing_days = spacing_days
        self._tolerance_days = tolerance_days

    async def plan(self, aoi: Aoi, date_range: DateRange | None = None) -> ScenePlan:
        """With no range: the last `window_days`, newest pass back in steps of `spacing_days`.

        With a range: the pass nearest each of `max_images` evenly spaced targets inside it.
        """
        if date_range is None:
            end = self._clock()
            start = end - timedelta(days=self._window_days)
        else:
            start = datetime.combine(date_range[0], time.min, tzinfo=UTC)
            end = datetime.combine(date_range[1], END_OF_DAY, tzinfo=UTC)
        scenes = dedupe_scenes(scenes=await self._catalog.search(aoi=aoi, start=start, end=end))
        group = choose_group(scenes=scenes)
        if group is None:
            return ScenePlan(
                status=PlanStatus.NO_COVERAGE,
                aoi=aoi,
                window_start=start,
                window_end=end,
                notes=["no NISAR L-band GCOV scene covers this area in the planning window"],
            )
        members = [
            scene
            for scene in scenes
            if (scene.track, scene.direction, scene.frame, scene.code, scene.mode)
            == (group.track, group.direction, group.frame, group.code, group.mode)
        ]
        selected = (
            select_dates(
                scenes=members,
                max_images=self._max_images,
                spacing_days=self._spacing_days,
                tolerance_days=self._tolerance_days,
            )
            if date_range is None
            else select_spread(scenes=members, start=start, end=end, max_images=self._max_images)
        )
        # Members come from the window only, so the top-up never leaves the user's range.
        if len(selected) < self._min_images:
            remaining = [scene for scene in reversed(members) if scene not in selected]
            selected = sorted(
                [*selected, *remaining[: self._min_images - len(selected)]],
                key=lambda scene: scene.acquired_at,
            )
        return ScenePlan(
            status=self._status(selected=selected),
            aoi=aoi,
            window_start=start,
            window_end=end,
            group=group,
            scenes=selected,
            passes=[
                ScenePass(acquired_at=scene.acquired_at, granule_id=scene.granule_id)
                for scene in members
            ],
            maturity_mixed=len({scene.maturity for scene in selected}) > 1,
            notes=self._notes(selected=selected),
        )

    def _status(self, selected: list[Scene]) -> PlanStatus:
        if len(selected) >= self._min_images:
            return PlanStatus.READY
        return PlanStatus.INSUFFICIENT_HISTORY

    def _notes(self, selected: list[Scene]) -> list[str]:
        notes: list[str] = []
        if len(selected) < self._min_images:
            dates = ", ".join(f"{scene.acquired_at:%Y-%m-%d}" for scene in selected)
            notes.append(
                f"only {len(selected)} usable dates found ({dates}); "
                f"the baseline lens needs at least {self._min_images} dates"
            )
        coverage = mean(scene.coverage for scene in selected)
        if coverage < FULL_COVERAGE:
            notes.append(f"the scenes cover about {coverage:.0%} of the area")
        return notes
