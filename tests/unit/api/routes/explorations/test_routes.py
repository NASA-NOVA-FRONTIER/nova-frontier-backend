import json
from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import create_engine

from nisar_hazard_watch.adapters.db.models import Base
from nisar_hazard_watch.adapters.runners.in_process_runner import InProcessRunner
from nisar_hazard_watch.api.app import create_app
from nisar_hazard_watch.config.settings import Settings
from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.constants.explorations import RunnerKind
from nisar_hazard_watch.constants.headers import REQUEST_ID_HEADER
from tests.factories import QADIRABAD_LAT, QADIRABAD_LON

FIXTURE = Path(__file__).parents[4] / "fixtures" / "asf_qadirabad.json"
ALLOWED_ORIGIN = "https://nova-frontier-frontend.vercel.app"
POINT = {"type": "Point", "coordinates": [QADIRABAD_LON, QADIRABAD_LAT]}
HUGE_POLYGON = {
    "type": "Polygon",
    "coordinates": [[[0.0, 0.0], [0.3, 0.0], [0.3, 0.3], [0.0, 0.3], [0.0, 0.0]]],
}
BODY = {"lens": "flood_wetland", "geometry": POINT}
URL = "/api/v1/explorations"
FIRMS_KEY = "a-firms-map-key"
FIRMS_HEADER = (
    "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,"
    "version,bright_ti5,frp,daynight"
)
WILDFIRE_BODY = {"lens": "wildfire", "geometry": POINT}
LONG_RUN_SECONDS = 10_000
# Series 084_A_018 in the ASF fixture, and the five that a 1 Jun to 11 Nov range picks.
SERIES_DAYS = [
    "2026-06-20",
    "2026-07-02",
    "2026-07-14",
    "2026-07-26",
    "2026-08-19",
    "2026-08-31",
    "2026-09-12",
    "2026-09-24",
    "2026-10-06",
    "2026-10-18",
    "2026-10-30",
    "2026-11-11",
]
RANGE_PICKS = ["2026-06-20", "2026-07-14", "2026-08-19", "2026-10-06", "2026-11-11"]
FORWARDED_FOR = "X-Forwarded-For"
EDGE_HOP = "100.64.0.1"


def _asf_catalog(status: int = 200, features: list | None = None) -> httpx.MockTransport:
    body = json.loads(FIXTURE.read_text())
    if features is not None:
        body["features"] = features
    return httpx.MockTransport(lambda request: httpx.Response(status_code=status, json=body))


@pytest.fixture
def start_api(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> Iterator[Callable[..., TestClient]]:
    clients: list[TestClient] = []

    def start(
        runner: InProcessRunner | None = None,
        asf: httpx.MockTransport | None = None,
        firms: httpx.MockTransport | None = None,
        **setting_overrides: object,
    ) -> TestClient:
        database = tmp_path / f"api-{len(clients)}.db"
        engine = create_engine(f"sqlite:///{database}")
        Base.metadata.create_all(engine)
        engine.dispose()
        settings = make_settings(
            **{
                "database_url": f"sqlite+aiosqlite:///{database}",
                "cors_allowed_origins": [ALLOWED_ORIGIN],
                "runner": RunnerKind.IN_PROCESS,
                "rate_limit_per_minute": 1000,
                **setting_overrides,
            }
        )
        app = create_app(
            settings=settings,
            asf_transport=asf or _asf_catalog(),
            firms_transport=firms,
            runner=runner or InProcessRunner(),
        )
        client = TestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield start
    for client in clients:
        client.__exit__(None, None, None)


def test_a_finished_exploration_answers_200_with_camel_case_fields_and_honest_labels(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.post(url=URL, json=BODY)

    # Assert
    body = response.json()
    assert response.status_code == 200
    assert body["id"].startswith("exp_")
    assert body["status"] == "succeeded"
    assert body["cache"] == "miss"
    assert body["plan"]["seriesKey"] == "084_A_018_4005_DHDH"
    assert len(body["plan"]["dates"]) == 5
    assert body["result"]["scientificStatus"] == "diagnostic"
    assert body["result"]["isDemo"] is True
    assert body["result"]["limitations"]
    assert body["result"]["layers"][0]["url"] == f"{URL}/{body['id']}/layers/display_synthetic"
    assert "etaSeconds" in body
    assert response.headers[REQUEST_ID_HEADER]


def test_a_running_exploration_answers_202_and_can_be_polled_and_cancelled(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(runner=InProcessRunner(duration_seconds=LONG_RUN_SECONDS))

    # Act
    created = client.post(url=URL, json=BODY)
    exploration_id = created.json()["id"]
    polled = client.get(url=f"{URL}/{exploration_id}")
    cancelled = client.delete(url=f"{URL}/{exploration_id}")

    # Assert
    assert created.status_code == 202
    assert created.json()["status"] == "running"
    assert polled.json()["status"] == "running"
    assert polled.json()["etaRemainingSeconds"] is not None
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["error"]["reasonCode"] == ReasonCode.CANCELLED


def test_the_same_request_twice_is_a_cache_hit(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api()
    first = client.post(url=URL, json=BODY).json()

    # Act
    second = client.post(url=URL, json=BODY)

    # Assert
    assert second.status_code == 200
    assert second.json()["cache"] == "hit"
    assert second.json()["id"] == first["id"]


def test_a_layer_redirects_to_the_runners_artifact(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api()
    created = client.post(url=URL, json=BODY).json()

    # Act
    response = client.get(
        url=f"{URL}/{created['id']}/layers/display_synthetic", follow_redirects=False
    )
    missing = client.get(url=f"{URL}/{created['id']}/layers/nope", follow_redirects=False)

    # Assert
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://")
    assert missing.status_code == 404


@pytest.mark.parametrize(
    argnames=("body", "status", "reason"),
    argvalues=[
        ({**BODY, "source": "S"}, 422, ReasonCode.SOURCE_NOT_AVAILABLE),
        (
            {**BODY, "geometry": {"type": "Point", "coordinates": [500, 0]}},
            422,
            ReasonCode.INVALID_GEOMETRY,
        ),
        ({**BODY, "geometry": HUGE_POLYGON}, 422, ReasonCode.AREA_TOO_LARGE),
        ({**BODY, "lens": "landslide"}, 422, ReasonCode.INVALID_REQUEST),
        ({**BODY, "unexpected": True}, 422, ReasonCode.INVALID_REQUEST),
        ({"geometry": POINT}, 422, ReasonCode.INVALID_REQUEST),
    ],
    ids=["s-band", "bad-point", "too-large", "unknown-lens", "extra-field", "missing-lens"],
)
def test_invalid_requests_are_422_problems_with_their_reason_code(
    start_api: Callable[..., TestClient], body: dict, status: int, reason: ReasonCode
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.post(url=URL, json=body)

    # Assert
    assert response.status_code == status
    assert response.json()["reasonCode"] == reason


def test_a_failing_catalog_is_a_502_with_its_reason(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(asf=_asf_catalog(status=503))

    # Act
    response = client.post(url=URL, json=BODY)

    # Assert
    assert response.status_code == 502
    assert response.json()["reasonCode"] == ReasonCode.UPSTREAM_CATALOG_ERROR


def test_an_area_without_scenes_is_a_final_no_data_answer(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(asf=_asf_catalog(features=[]))

    # Act
    response = client.post(url=URL, json=BODY)

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "noData"
    assert response.json()["error"]["reasonCode"] == ReasonCode.NO_COVERAGE


def test_a_full_queue_is_a_503_with_its_reason(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(
        runner=InProcessRunner(duration_seconds=LONG_RUN_SECONDS), max_active_explorations=1
    )
    client.post(url=URL, json=BODY)

    # Act
    response = client.post(url=URL, json={**BODY, "lens": "wildfire"})

    # Assert
    assert response.status_code == 503
    assert response.json()["reasonCode"] == ReasonCode.QUEUE_FULL


def test_each_client_is_limited_on_its_own_and_gets_a_429(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(rate_limit_per_minute=2)
    first_client = {FORWARDED_FOR: f"203.0.113.7, {EDGE_HOP}"}
    other_client = {FORWARDED_FOR: f"198.51.100.9, {EDGE_HOP}"}

    # Act
    allowed = [client.post(url=URL, json=BODY, headers=first_client).status_code for _ in range(2)]
    limited = client.post(url=URL, json=BODY, headers=first_client)
    other = client.post(url=URL, json=BODY, headers=other_client)

    # Assert
    assert allowed == [200, 200]
    assert limited.status_code == 429
    assert limited.json()["reasonCode"] == ReasonCode.RATE_LIMITED
    assert other.status_code == 200


def test_a_spoofed_leading_forwarded_address_does_not_dodge_the_limit(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(rate_limit_per_minute=1)
    first = {FORWARDED_FOR: f"192.0.2.1, 203.0.113.7, {EDGE_HOP}"}
    second = {FORWARDED_FOR: f"192.0.2.2, 203.0.113.7, {EDGE_HOP}"}

    # Act
    allowed = client.post(url=URL, json=BODY, headers=first)
    limited = client.post(url=URL, json=BODY, headers=second)

    # Assert
    assert allowed.status_code == 200
    assert limited.status_code == 429


def test_without_trusted_proxies_the_forwarded_header_is_ignored(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(rate_limit_per_minute=1, trusted_proxy_hops=0)

    # Act
    allowed = client.post(url=URL, json=BODY, headers={FORWARDED_FOR: "203.0.113.7"})
    limited = client.post(url=URL, json=BODY, headers={FORWARDED_FOR: "198.51.100.9"})

    # Assert
    assert allowed.status_code == 200
    assert limited.status_code == 429


def test_an_oversized_body_is_refused_before_it_is_read(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()
    padding = {"type": "Point", "coordinates": [0, 0], "padding": "x" * 20_000}

    # Act
    response = client.post(url=URL, json={**BODY, "geometry": padding})

    # Assert
    assert response.status_code == 413
    assert response.json()["reasonCode"] == ReasonCode.PAYLOAD_TOO_LARGE


def test_unknown_and_malformed_ids_are_rejected(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api()

    # Act
    unknown = client.get(url=f"{URL}/exp_0000000000000000")
    malformed = client.get(url=f"{URL}/not-an-id")

    # Assert
    assert unknown.status_code == 404
    assert unknown.json()["reasonCode"] == ReasonCode.NOT_FOUND
    assert malformed.status_code == 422


def test_the_lens_catalog_lists_the_supported_lenses_including_the_insar_pair(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.get(url="/api/v1/lenses")

    # Assert
    lenses = {lens["id"]: lens for lens in response.json()}
    assert set(lenses) == {
        "flood_wetland",
        "vegetation_disturbance",
        "wildfire",
        "agriculture",
        "insar",
    }
    assert lenses["agriculture"]["opticalEvidence"] is False
    assert lenses["flood_wetland"]["minimumDates"] == 4
    assert lenses["insar"]["minimumDates"] == 2


def test_coverage_describes_the_plan_for_a_point(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.get(
        url="/api/v1/coverage", params={"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT}
    )
    invalid = client.get(url="/api/v1/coverage", params={"lon": 500, "lat": 0})

    # Assert
    assert response.status_code == 200
    assert response.json()["plan"]["status"] == "ready"
    assert response.json()["plan"]["seriesKey"] == "084_A_018_4005_DHDH"
    assert invalid.status_code == 422


def test_coverage_estimates_the_lens_it_is_asked_about(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()
    point = {"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT}

    # Act
    default = client.get(url="/api/v1/coverage", params=point)
    wildfire = client.get(
        url="/api/v1/coverage", params={**point, "lens": "wildfire", "opticalEvidence": "true"}
    )
    unknown = client.get(url="/api/v1/coverage", params={**point, "lens": "volcano"})

    # Assert
    assert default.status_code == 200
    assert default.json()["lens"] == "flood_wetland"
    assert default.json()["cache"] == "miss"
    assert default.json()["etaSeconds"] > 0
    assert default.json()["grid"] is None
    assert wildfire.json()["lens"] == "wildfire"
    assert unknown.status_code == 422


def test_coverage_checks_the_cache_with_the_optical_evidence_it_is_sent(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()
    point = {"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT}
    client.post(url=URL, json={**BODY, "opticalEvidence": True})

    # Act
    flood_default = client.get(url="/api/v1/coverage", params=point)
    with_optical = client.get(url="/api/v1/coverage", params={**point, "opticalEvidence": "true"})
    without_optical = client.get(
        url="/api/v1/coverage", params={**point, "opticalEvidence": "false"}
    )

    # Assert
    assert flood_default.json()["cache"] == "hit"
    assert flood_default.json()["etaSeconds"] == 0
    assert with_optical.json()["cache"] == "hit"
    assert without_optical.json()["cache"] == "miss"


def test_an_exploration_and_its_coverage_take_a_date_range(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()
    dates = {"startDate": "2026-06-01", "endDate": "2026-11-11"}
    point = {"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT, **dates}

    # Act
    created = client.post(url=URL, json={**BODY, **dates})
    coverage = client.get(url="/api/v1/coverage", params=point)

    # Assert
    plan = created.json()["plan"]
    assert created.status_code in (200, 202)
    assert plan["dates"] == RANGE_PICKS
    assert (plan["windowStart"], plan["windowEnd"]) == ("2026-06-01", "2026-11-11")
    assert coverage.json()["plan"]["dates"] == RANGE_PICKS
    assert [item["acquiredAt"][:10] for item in coverage.json()["passes"]] == SERIES_DAYS


def test_a_date_range_that_cannot_be_planned_is_a_422_with_its_own_reason(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()
    reversed_dates = {"startDate": "2026-10-31", "endDate": "2026-06-01"}

    # Act
    created = client.post(url=URL, json={**BODY, **reversed_dates})
    coverage = client.get(
        url="/api/v1/coverage",
        params={"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT, "startDate": "2026-06-01"},
    )

    # Assert
    for response in (created, coverage):
        assert response.status_code == 422
        assert response.json()["reasonCode"] == ReasonCode.INVALID_DATE_RANGE


# The series in the ASF fixture, ranked as the planner chooses (#4): the ascending one first.
FIXTURE_SERIES = [
    "084_A_018_4005_DHDH",
    "063_D_072_4005_DHDH",
    "135_D_072_4005_DHDH",
    "135_D_072_2005_DHDH",
    "135_D_072_2005_QPDH",
    "063_D_072_2005_DHDH",
    "063_D_072_2005_QPDH",
]


def test_coverage_lists_every_series_it_found_with_its_direction_and_dates(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.get(
        url="/api/v1/coverage", params={"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT}
    )

    # Assert
    series = response.json()["series"]
    assert [item["seriesKey"] for item in series] == FIXTURE_SERIES
    assert series[0]["seriesKey"] == response.json()["plan"]["seriesKey"]
    assert {item["direction"] for item in series} == {"A", "D"}
    assert series[0] | {"dates": None} == {
        "seriesKey": "084_A_018_4005_DHDH",
        "direction": "A",
        "track": 84,
        "frame": 18,
        "code": "4005",
        "mode": "DHDH",
        "dates": None,
        "coverage": 1.0,
        "dualPol": True,
    }
    assert series[0]["dates"] == [day for day in SERIES_DAYS if day in series[0]["dates"]]


def test_an_exploration_and_its_coverage_follow_the_direction_or_series_asked_for(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()
    point = {"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT}

    # Act
    descending = client.post(url=URL, json={**BODY, "direction": "D"})
    chosen = client.post(url=URL, json={**BODY, "seriesKey": "135_D_072_2005_QPDH"})
    coverage = client.get(url="/api/v1/coverage", params={**point, "direction": "D"})
    by_key = client.get(
        url="/api/v1/coverage", params={**point, "seriesKey": "135_D_072_2005_QPDH"}
    )

    # Assert
    assert descending.status_code in (200, 202)
    assert descending.json()["plan"]["seriesKey"] == "063_D_072_4005_DHDH"
    assert chosen.json()["plan"]["seriesKey"] == "135_D_072_2005_QPDH"
    assert coverage.json()["plan"]["seriesKey"] == "063_D_072_4005_DHDH"
    assert by_key.json()["plan"]["seriesKey"] == "135_D_072_2005_QPDH"
    # The list never narrows, so the client can still offer the other direction.
    assert [item["seriesKey"] for item in coverage.json()["series"]] == FIXTURE_SERIES


def test_a_direction_or_series_with_nothing_here_is_the_usual_no_coverage_answer(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange: only the ascending series is left in the catalog.
    body = json.loads(FIXTURE.read_text())
    ascending = [
        feature
        for feature in body["features"]
        if "_084_A_018_" in feature["properties"]["sceneName"]
    ]
    client = start_api(asf=_asf_catalog(features=ascending))
    point = {"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT}

    # Act
    created = client.post(url=URL, json={**BODY, "direction": "D"})
    unknown = client.post(url=URL, json={**BODY, "seriesKey": "999_A_001_4005_DHDH"})
    coverage = client.get(url="/api/v1/coverage", params={**point, "direction": "D"})

    # Assert
    for response in (created, unknown):
        assert response.status_code == 200
        assert response.json()["status"] == "noData"
        assert response.json()["error"]["reasonCode"] == ReasonCode.NO_COVERAGE
    assert "descending series" in created.json()["error"]["detail"]
    assert coverage.json()["plan"]["status"] == "noCoverage"
    assert coverage.json()["etaSeconds"] is None
    assert [item["seriesKey"] for item in coverage.json()["series"]] == ["084_A_018_4005_DHDH"]


@pytest.mark.parametrize(
    "extra",
    [
        {"direction": "north"},
        {"seriesKey": "084_A_018"},
        {"direction": "A", "seriesKey": "063_D_072_4005_DHDH"},
    ],
)
def test_a_series_choice_that_cannot_hold_is_a_422(
    start_api: Callable[..., TestClient], extra: dict[str, str]
) -> None:
    # Arrange
    client = start_api()

    # Act
    created = client.post(url=URL, json={**BODY, **extra})
    coverage = client.get(
        url="/api/v1/coverage", params={"lon": QADIRABAD_LON, "lat": QADIRABAD_LAT, **extra}
    )

    # Assert
    for response in (created, coverage):
        assert response.status_code == 422
        assert response.json()["reasonCode"] == ReasonCode.INVALID_REQUEST


def test_the_insar_lens_takes_its_direction_from_its_pair(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()
    # A real pair (tests/fixtures/ml_gateway_case_series_gunw.json).
    pair = (
        "NISAR_L2_PR_GUNW_025_024_A_018_026_4000_SH_20260709T202900_20260709T202935"
        "_20260721T202900_20260721T202934_P05023_N_F_J_001"
    )

    # Act
    response = client.post(
        url=URL, json={"lens": "insar", "geometry": POINT, "pairId": pair, "direction": "A"}
    )

    # Assert
    assert response.status_code == 422
    assert "insar" in response.json()["detail"]


def test_the_openapi_document_lists_the_new_endpoints(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()

    # Act
    paths = client.get(url="/openapi.json").json()["paths"]

    # Assert
    assert URL in paths
    assert f"{URL}/{{exploration_id}}" in paths
    assert f"{URL}/{{exploration_id}}/layers/{{layer_id}}" in paths
    assert "/api/v1/lenses" in paths
    assert "/api/v1/coverage" in paths


KUMAMOTO_PAIR = (
    "NISAR_L2_PR_GUNW_026_024_A_018_028_4000_SH_20260721T202900_20260721T202934_"
    "20260814T202858_20260814T202933_P05023_N_F_J_001"
)
KUMAMOTO_POINT = {"type": "Point", "coordinates": [130.65, 32.65]}


def test_an_insar_pair_is_answered_without_a_gcov_scene_catalog(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(asf=_asf_catalog(status=503))
    body = {"lens": "insar", "geometry": KUMAMOTO_POINT, "pairId": KUMAMOTO_PAIR}

    # Act
    response = client.post(url=URL, json=body)

    # Assert
    answer = response.json()
    assert response.status_code == 200
    assert answer["status"] == "succeeded"
    assert answer["lens"] == "insar"
    assert answer["result"]["windowStart"] == "2026-07-21"
    assert answer["result"]["windowEnd"] == "2026-08-14"
    assert answer["result"]["scenes"] == []
    assert any("no displacement is reported" in text for text in answer["result"]["limitations"])


def test_an_insar_question_without_a_pair_is_a_422_problem(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()

    # Act
    response = client.post(url=URL, json={"lens": "insar", "geometry": KUMAMOTO_POINT})

    # Assert
    assert response.status_code == 422
    assert response.json()["reasonCode"] == ReasonCode.INVALID_REQUEST


def test_a_name_that_is_not_a_usable_pair_is_a_422_problem(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api()
    reversed_pair = KUMAMOTO_PAIR.replace("20260814T202858", "20260601T202858")
    body = {"lens": "insar", "geometry": KUMAMOTO_POINT, "pairId": reversed_pair}

    # Act
    response = client.post(url=URL, json=body)

    # Assert
    assert response.status_code == 422
    assert response.json()["reasonCode"] == ReasonCode.INVALID_REQUEST


class _FirmsAnswers:
    """One detection inside the area on the last day of every chunk it is asked about."""

    def __init__(self) -> None:
        self.requests = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests += 1
        *_, days, start = str(request.url).split("/")
        last_day = date.fromisoformat(start) + timedelta(days=int(days) - 1)
        row = (
            f"{QADIRABAD_LAT},{QADIRABAD_LON},330.1,0.4,0.4,{last_day.isoformat()},2359,N20,"
            "nominal,2.0NRT,300.2,4.5,N"
        )
        return httpx.Response(status_code=200, text=f"{FIRMS_HEADER}\n{row}\n")


def test_a_wildfire_answer_carries_the_fire_context_apart_from_the_radar_lens(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    answers = _FirmsAnswers()
    client = start_api(firms=httpx.MockTransport(answers), firms_map_key=SecretStr(FIRMS_KEY))

    # Act
    response = client.post(url=URL, json=WILDFIRE_BODY)

    # Assert
    context = response.json()["result"]["fireContext"]
    assert response.status_code == 200
    assert context["status"] == "available"
    assert context["detections"] >= 1
    assert context["peakFrpMw"] == 4.5
    assert context["source"].startswith("NASA FIRMS")
    assert answers.requests > 0


def test_without_a_firms_key_the_wildfire_answer_says_it_is_radar_only(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    answers = _FirmsAnswers()
    client = start_api(firms=httpx.MockTransport(answers))

    # Act
    response = client.post(url=URL, json=WILDFIRE_BODY)

    # Assert
    context = response.json()["result"]["fireContext"]
    assert context["status"] == "notConfigured"
    assert "radar-only" in context["note"]
    assert answers.requests == 0


def test_a_flood_answer_has_no_fire_context(start_api: Callable[..., TestClient]) -> None:
    # Arrange
    client = start_api(firms_map_key=SecretStr(FIRMS_KEY))

    # Act
    response = client.post(url=URL, json=BODY)

    # Assert
    assert response.json()["result"].get("fireContext") is None


def test_a_client_over_its_daily_limit_gets_429_with_retry_after_and_the_limits_follow(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(daily_limit_client=1)
    client.post(url=URL, json=BODY)

    # Act
    refused = client.post(url=URL, json={**BODY, "lens": "vegetation_disturbance"})
    limits = client.get(url="/api/v1/limits").json()

    # Assert
    assert refused.status_code == 429
    assert refused.json()["reasonCode"] == ReasonCode.DAILY_LIMIT_REACHED
    assert int(refused.headers["Retry-After"]) > 0
    assert limits["remainingClient"] == 0
    assert limits["remainingApp"] == limits["limitApp"] - 1


def test_the_minute_rate_limit_also_tells_the_client_when_to_retry(
    start_api: Callable[..., TestClient],
) -> None:
    # Arrange
    client = start_api(rate_limit_per_minute=1)
    client.post(url=URL, json=BODY)

    # Act
    refused = client.post(url=URL, json=BODY)

    # Assert
    assert refused.status_code == 429
    assert refused.json()["reasonCode"] == ReasonCode.RATE_LIMITED
    assert 0 < int(refused.headers["Retry-After"]) <= 60


def test_the_gateway_receives_the_shared_secret_when_a_new_exploration_starts(
    make_settings: Callable[..., Settings], tmp_path: Path
) -> None:
    # Arrange
    database = tmp_path / "gateway.db"
    engine = create_engine(f"sqlite:///{database}")
    Base.metadata.create_all(engine)
    engine.dispose()
    seen: list[httpx.Request] = []

    def gateway(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            status_code=202,
            json={"job_id": "a" * 32, "status": "queued", "cache": "miss", "result": None},
        )

    settings = make_settings(
        database_url=f"sqlite+aiosqlite:///{database}",
        runner=RunnerKind.GATEWAY,
        gateway_shared_secret=SecretStr("a-long-shared-secret-value"),
    )
    app = create_app(
        settings=settings,
        asf_transport=_asf_catalog(),
        gateway_transport=httpx.MockTransport(gateway),
    )

    # Act
    with TestClient(app) as client:
        response = client.post(url=URL, json=BODY)

    # Assert
    assert response.status_code == 202
    assert seen[0].headers["Authorization"] == "Bearer a-long-shared-secret-value"
    assert "a-long-shared-secret-value" not in response.text
