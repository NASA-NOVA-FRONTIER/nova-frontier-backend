from datetime import date, datetime
from typing import Any, Self

from pydantic import ConfigDict, Field, model_validator

from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.explorations import (
    CacheState,
    ExplorationStatus,
    Lens,
    SourceBand,
    Stage,
    StageName,
    StageState,
)
from nisar_hazard_watch.constants.insar import (
    DEFAULT_COHERENCE_THRESHOLD,
    GUNW_NAME_PATTERN,
    MAX_COHERENCE_THRESHOLD,
    MIN_COHERENCE_THRESHOLD,
)
from nisar_hazard_watch.constants.sar import (
    SERIES_KEY_PATTERN,
    Configuration,
    Direction,
    Maturity,
    PlanStatus,
)
from nisar_hazard_watch.models.base_model import CamelModel
from nisar_hazard_watch.models.fire_context import FireContext
from nisar_hazard_watch.models.insar_summary import InsarSummary
from nisar_hazard_watch.models.scene import ScenePass, SeriesOption
from nisar_hazard_watch.models.science_products import ScienceProducts
from nisar_hazard_watch.utils.series_choice import series_choice_problem


class ExplorationRequest(CamelModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "lens": "flood_wetland",
                    "geometry": {"type": "Point", "coordinates": [73.6967, 32.3214]},
                    "opticalEvidence": True,
                    "startDate": "2026-06-01",
                    "endDate": "2026-10-31",
                }
            ]
        },
    )

    lens: Lens
    geometry: dict[str, Any]
    source: SourceBand = SourceBand.L_BAND
    optical_evidence: bool = False
    pair_id: str | None = Field(default=None, pattern=GUNW_NAME_PATTERN)
    coherence_threshold: float | None = Field(
        default=None, ge=MIN_COHERENCE_THRESHOLD, le=MAX_COHERENCE_THRESHOLD, allow_inf_nan=False
    )
    # Both or neither; without them the planner reads its default window (the last 152 days).
    start_date: date | None = None
    end_date: date | None = None
    # Either or both, from GET /api/v1/coverage `series`; without them the planner picks one itself.
    direction: Direction | None = None
    series_key: str | None = Field(default=None, pattern=SERIES_KEY_PATTERN)

    @model_validator(mode="after")
    def _series_choice_is_consistent(self) -> Self:
        if self.lens is Lens.INSAR and (self.direction is not None or self.series_key is not None):
            raise ValueError(
                "direction and seriesKey don't apply to the insar lens: its pair sets them"
            )
        problem = series_choice_problem(direction=self.direction, series_key=self.series_key)
        if problem is not None:
            raise ValueError(problem)
        return self

    @model_validator(mode="after")
    def _pair_belongs_to_the_insar_lens(self) -> Self:
        if self.lens is Lens.INSAR:
            if self.pair_id is None:
                raise ValueError("the insar lens needs a pairId from GET /api/v1/insar/pairs")
            if self.coherence_threshold is None:
                self.coherence_threshold = DEFAULT_COHERENCE_THRESHOLD
        elif self.pair_id is not None or self.coherence_threshold is not None:
            raise ValueError("pairId and coherenceThreshold apply to the insar lens only")
        return self


class StageTiming(CamelModel):
    name: StageName
    state: StageState
    seconds: float | None = None
    budget_seconds: float | None = None


class Progress(CamelModel):
    scenes_read: int | None = None
    scenes_total: int


class ProblemInfo(CamelModel):
    reason_code: ReasonCode
    detail: str


class ExplorationScene(CamelModel):
    granule_id: str
    acquired_at: datetime
    track: int
    direction: Direction
    frame: int
    mode: str
    maturity: Maturity
    configuration: Configuration
    crid: str
    version: int
    coverage: float


class Layer(CamelModel):
    id: str
    title: str
    kind: str
    units: str
    colormap: str
    bounds: tuple[float, float, float, float]
    url: str
    legend: dict[str, str] | None = None
    value_range: tuple[float, float] | None = None
    crs: str | None = None
    grid: dict[str, Any] | None = None
    dates: list[str] | None = None


class PlanSummary(CamelModel):
    status: PlanStatus
    series_key: str | None = None
    dates: list[date] = Field(default_factory=list)
    maturity_mixed: bool = False
    notes: list[str] = Field(default_factory=list)
    # The window the catalog was read over: the user's range, or the default one.
    window_start: date | None = None
    window_end: date | None = None


class ExplorationResult(CamelModel):
    geometry: dict[str, Any]
    area_km2: float
    window_start: date
    window_end: date
    scenes: list[ExplorationScene]
    observations: list[dict[str, Any]]
    lens: dict[str, Any] | None
    aoi_summary: dict[str, Any] | None
    layers: list[Layer]
    quality: dict[str, Any]
    limitations: list[str]
    scientific_status: str
    timings: dict[str, float]
    is_demo: bool = False
    insar: InsarSummary | None = None
    fire_context: FireContext | None = None
    products: ScienceProducts | None = None


class ExplorationView(CamelModel):
    id: str
    status: ExplorationStatus
    stage: Stage
    lens: Lens
    source: SourceBand
    cache: CacheState
    eta_seconds: float | None = None
    eta_remaining_seconds: float | None = None
    elapsed_seconds: float
    stages: list[StageTiming] = Field(default_factory=list)
    progress: Progress | None = None
    queue_position: int | None = None
    plan: PlanSummary | None = None
    result: ExplorationResult | None = None
    error: ProblemInfo | None = None


class CoverageGrid(CamelModel):
    width: int
    height: int
    posting_m: float


class CoverageView(CamelModel):
    plan: PlanSummary
    area_km2: float
    warnings: list[str] = Field(default_factory=list)
    precomputed_case: str | None = None
    # What running `lens` here would cost. All three stay null when nothing would run (no coverage,
    # no scenes, or the insar lens, whose pair is chosen later); a cache hit answers at once.
    lens: Lens
    eta_seconds: float | None = None
    cache: CacheState | None = None
    # The grid is only known once a job ran, so it comes from a cached answer and is null otherwise.
    grid: CoverageGrid | None = None
    # Every pass of the chosen series in the window, oldest first; plan.dates are the ones picked.
    passes: list[ScenePass] = Field(default_factory=list)
    # Every series found in the window, the planner's default first (plan.seriesKey when it is
    # unfiltered). Pass a `direction` or a `seriesKey` from here to plan and explore that one.
    series: list[SeriesOption] = Field(default_factory=list)


class LensInfo(CamelModel):
    id: Lens
    title: str
    description: str
    optical_evidence: bool
    minimum_dates: int
