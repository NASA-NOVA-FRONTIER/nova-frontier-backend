from datetime import date, datetime

from pydantic import Field, computed_field

from nisar_hazard_watch.constants.sar import Configuration, Direction, Maturity, PlanStatus
from nisar_hazard_watch.models.base_model import CamelModel
from nisar_hazard_watch.models.geometry import Aoi


class SceneIdentity(CamelModel):
    granule_id: str
    acquired_at: datetime
    cycle: int
    track: int
    direction: Direction
    frame: int
    code: str
    mode: str
    polarizations: list[str]
    maturity: Maturity
    configuration: Configuration
    crid: str
    version: int
    url: str


class Scene(SceneIdentity):
    coverage: float


class SceneGroup(CamelModel):
    track: int
    direction: Direction
    frame: int
    code: str
    mode: str

    @computed_field
    @property
    def series_key(self) -> str:
        """Same identity the ML service uses: scenes of one key share a grid and can be stacked."""
        return f"{self.track:03d}_{self.direction.value}_{self.frame:03d}_{self.code}_{self.mode}"


class SeriesOption(CamelModel):
    """One series found over the area: what a client can pick by `direction` or `seriesKey`."""

    series_key: str
    direction: Direction
    track: int
    frame: int
    code: str
    mode: str
    # Every distinct day this series measured in the window, oldest first.
    dates: list[date]
    coverage: float
    dual_pol: bool


class ScenePass(CamelModel):
    acquired_at: datetime
    granule_id: str


class ScenePlan(CamelModel):
    status: PlanStatus
    aoi: Aoi
    window_start: datetime
    window_end: datetime
    group: SceneGroup | None = None
    scenes: list[Scene] = Field(default_factory=list)
    # Every pass of the chosen group in the window, oldest first; `scenes` are the ones picked.
    passes: list[ScenePass] = Field(default_factory=list)
    # Every series found in the window, ranked as the planner chooses: the first is its default.
    series: list[SeriesOption] = Field(default_factory=list)
    maturity_mixed: bool = False
    notes: list[str] = Field(default_factory=list)
