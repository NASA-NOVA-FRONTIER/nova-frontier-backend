from datetime import datetime

from nisar_hazard_watch.models.base_model import CamelModel


class DailyLimitsView(CamelModel):
    """What is left of today's new analyses, for the whole app and for the asking client."""

    remaining_app: int
    remaining_client: int
    resets_at: datetime
    limit_app: int
    limit_client: int
