import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from nisar_hazard_watch.exceptions.exploration_errors import DailyLimitReachedError
from nisar_hazard_watch.models.limits import DailyLimitsView
from nisar_hazard_watch.ports.job_repository import JobRepository
from nisar_hazard_watch.utils.client_hash import hash_client_key


def _utc_now() -> datetime:
    return datetime.now(UTC)


class DailyLimits:
    """New analyses allowed per UTC day, for the whole app and for each client.

    Results served from a cache never spend the allowance: only runs submitted to the analysis
    service do, and the counts come from the jobs table, so a restart does not reset them.
    """

    def __init__(
        self,
        repository: JobRepository,
        app_limit: int,
        client_limit: int,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self._repository = repository
        self._app_limit = app_limit
        self._client_limit = client_limit
        self._clock = clock

    async def view(self, client: str | None) -> DailyLimitsView:
        start = self._clock().replace(hour=0, minute=0, second=0, microsecond=0)
        used_app = await self._repository.count_new_since(since=start)
        used_client = 0
        if client is not None:
            used_client = await self._repository.count_new_since(
                since=start, client_key=hash_client_key(client=client)
            )
        return DailyLimitsView(
            remaining_app=max(0, self._app_limit - used_app),
            remaining_client=max(0, self._client_limit - used_client),
            resets_at=start + timedelta(days=1),
            limit_app=self._app_limit,
            limit_client=self._client_limit,
        )

    async def require(self, client: str | None) -> None:
        view = await self.view(client=client)
        retry_after = max(1, math.ceil((view.resets_at - self._clock()).total_seconds()))
        if view.remaining_client == 0:
            raise DailyLimitReachedError(
                f"this client has used its {view.limit_client} new analyses for today; the known "
                "cases and results already computed stay available",
                retry_after_seconds=retry_after,
            )
        if view.remaining_app == 0:
            raise DailyLimitReachedError(
                f"the app has used its {view.limit_app} new analyses for today; the known cases "
                "and results already computed stay available",
                retry_after_seconds=retry_after,
            )
