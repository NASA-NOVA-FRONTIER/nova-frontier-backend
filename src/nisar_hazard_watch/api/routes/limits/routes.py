from fastapi import APIRouter

from nisar_hazard_watch.api.dependencies import ClientDep, DailyLimitsDep
from nisar_hazard_watch.models.limits import DailyLimitsView

router = APIRouter(tags=["limits"])


@router.get("", response_model=DailyLimitsView)
async def get_limits(client: ClientDep, limits: DailyLimitsDep) -> DailyLimitsView:
    return await limits.view(client=client)
