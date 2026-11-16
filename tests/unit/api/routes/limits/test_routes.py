from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from nisar_hazard_watch.adapters.db.models import Base
from nisar_hazard_watch.adapters.runners.in_process_runner import InProcessRunner
from nisar_hazard_watch.api.app import create_app
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.explorations import RunnerKind

URL = "/api/v1/limits"
APP_LIMIT = 40
CLIENT_LIMIT = 3
RESPONSE_FIELDS = {"remainingApp", "remainingClient", "resetsAt", "limitApp", "limitClient"}


@pytest.fixture
def client(make_settings: Callable[..., Settings], tmp_path: Path) -> Iterator[TestClient]:
    database = tmp_path / "limits.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    engine.dispose()
    settings = make_settings(
        database_url=f"sqlite+aiosqlite:///{database}",
        runner=RunnerKind.IN_PROCESS,
        daily_limit_app=APP_LIMIT,
        daily_limit_client=CLIENT_LIMIT,
    )
    with TestClient(create_app(settings=settings, runner=InProcessRunner())) as started:
        yield started


def test_the_limits_answer_with_what_is_left_for_the_app_and_for_the_client(
    client: TestClient,
) -> None:
    # Arrange
    expected_remaining = (APP_LIMIT, CLIENT_LIMIT)

    # Act
    response = client.get(url=URL)

    # Assert
    body = response.json()
    assert response.status_code == 200
    assert set(body) == RESPONSE_FIELDS
    assert (body["remainingApp"], body["remainingClient"]) == expected_remaining
    assert (body["limitApp"], body["limitClient"]) == expected_remaining


def test_the_reset_is_the_next_utc_midnight(client: TestClient) -> None:
    # Arrange
    today = datetime.now(UTC).date()

    # Act
    resets_at = datetime.fromisoformat(client.get(url=URL).json()["resetsAt"])

    # Assert
    assert resets_at.tzinfo is not None
    assert resets_at.date() > today
    assert (resets_at.hour, resets_at.minute, resets_at.second) == (0, 0, 0)
