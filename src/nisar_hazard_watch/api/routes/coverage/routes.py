from typing import Annotated

from fastapi import APIRouter, Query

from nisar_hazard_watch.api.dependencies import ExplorationServiceDep, RateLimit
from nisar_hazard_watch.constants.explorations import DEFAULT_COVERAGE_LENS, Lens
from nisar_hazard_watch.models.exploration import CoverageView

router = APIRouter(tags=["coverage"])

Longitude = Annotated[float, Query(ge=-180, le=180, allow_inf_nan=False)]
Latitude = Annotated[float, Query(ge=-90, le=90, allow_inf_nan=False)]
# Send the same lens and opticalEvidence as the exploration would, or the cache check can't match.
# Without opticalEvidence, the service assumes what the frontend sends for that lens.
LensQuery = Annotated[Lens, Query()]
OpticalEvidence = Annotated[bool | None, Query(alias="opticalEvidence")]


@router.get("", response_model=CoverageView, dependencies=[RateLimit])
async def get_coverage(
    lon: Longitude,
    lat: Latitude,
    service: ExplorationServiceDep,
    lens: LensQuery = DEFAULT_COVERAGE_LENS,
    optical_evidence: OpticalEvidence = None,
) -> CoverageView:
    return await service.coverage(
        geometry={"type": "Point", "coordinates": [lon, lat]},
        lens=lens,
        optical_evidence=optical_evidence,
    )
