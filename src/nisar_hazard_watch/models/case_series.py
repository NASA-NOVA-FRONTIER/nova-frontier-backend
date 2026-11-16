from datetime import date

from pydantic import ConfigDict, Field, JsonValue

from nisar_hazard_watch.constants.explorations import SCIENTIFIC_STATUS
from nisar_hazard_watch.models.base_model import CamelModel


class Relayed(CamelModel):
    """A row of the gateway's series: the fields the frontend reads, anything else dropped."""

    model_config = ConfigDict(extra="ignore")


class SeriesObservation(Relayed):
    """The radar return at the case's marker pixel on one date and channel."""

    date: date
    polarization: str
    gamma0_db: float | None = None
    granule: str | None = None


class SeriesGroup(Relayed):
    """The median and spatial interquartile range of one group of cells on one date and channel."""

    date: date
    polarization: str
    group: str
    cells: int
    median_db: float | None = None
    spatial_iqr_db: tuple[float, float] | None = None


class BandPass(Relayed):
    """How many cells left their own baseline band on one assessment date."""

    date: date
    outside_cells: int
    eligible_cells: int
    outside_percent: float | None = None


class SeriesInterval(Relayed):
    """One interferometric pair of a GUNW case: its dates and what its coherence supports."""

    reference_date: date
    secondary_date: date
    interval_days: int
    source_id: str | None = None
    median_coherence: float | None = None
    finite_cells: int | None = None
    total_cells: int | None = None
    coherent_component_fraction: float | None = None
    ionosphere_filled_fraction: float | None = None


class CaseSeriesView(CamelModel):
    """A known case's measured series: per-date values (GCOV) or pair intervals (GUNW)."""

    case_id: str
    point: tuple[float, float] | None = None
    selected_pixel: tuple[int, int] | None = None
    target_date: date | None = None
    observations: list[SeriesObservation] = Field(default_factory=list)
    observed_groups: list[SeriesGroup] = Field(default_factory=list)
    diagnostic_band_timeline: list[BandPass] = Field(default_factory=list)
    intervals: list[SeriesInterval] = Field(default_factory=list)
    spatial_iqr_semantics: str | None = None
    # Relayed as sent after the forbidden-word scrub; their keys change with the science. The
    # gateway's `area_readout` (median shifts over the window's cells) is renamed: keys naming an
    # area are never relayed, since the science estimates none.
    point_readout: dict[str, JsonValue] | None = None
    window_readout: dict[str, JsonValue] | None = None
    scientific_status: str = SCIENTIFIC_STATUS
