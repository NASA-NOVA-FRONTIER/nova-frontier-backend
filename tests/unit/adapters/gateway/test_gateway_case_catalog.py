import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nisar_hazard_watch.adapters.gateway.gateway_case_catalog import GatewayCaseCatalog
from nisar_hazard_watch.constants.cases import CASE_FALLBACK_LIMITATIONS
from nisar_hazard_watch.exceptions.case_errors import (
    CaseSeriesUnavailableError,
    CasesUnavailableError,
)
from nisar_hazard_watch.models.case import CaseView
from nisar_hazard_watch.models.science_products import RadarVisualization
from tests.honesty import forbidden_keys

FIXTURE = Path(__file__).parents[3] / "fixtures" / "ml_gateway_cases.json"
BASE_URL = "https://gateway.example.test"
CASE_IDS = ["chokwe", "qadirabad", "richmond", "kumamoto", "choco", "san-marcos"]
QADIRABAD_LAYER_URL = f"{BASE_URL}/v2/cases/qadirabad/layers/change_db_hh.png"


def _real_cases() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text())


class Recorder:
    def __init__(self, answer: httpx.Response | Exception) -> None:
        self.requests: list[httpx.Request] = []
        self._answer = answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


async def _cases(handler: Recorder) -> list[CaseView]:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await GatewayCaseCatalog(client=client, base_url=BASE_URL + "/").cases()


async def test_it_reads_every_real_case_in_the_gateway_order() -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=200, json=_real_cases()))

    # Act
    cases = await _cases(handler=handler)

    # Assert
    assert [case.id for case in cases] == CASE_IDS
    assert str(handler.requests[0].url) == f"{BASE_URL}/v2/cases"
    qadirabad = cases[1]
    assert (len(qadirabad.layers), len(qadirabad.visualizations)) == (8, 8)
    assert qadirabad.layers[0].url == QADIRABAD_LAYER_URL
    assert qadirabad.layers[0].value_range == (-8.0, 8.0)
    assert qadirabad.evidence.threshold_cells == 1911
    assert qadirabad.evidence.radar_support_cells == 16384
    assert len(qadirabad.limitations) == 7
    assert qadirabad.is_demo is False


@pytest.mark.parametrize(argnames="index", argvalues=range(len(CASE_IDS)), ids=CASE_IDS)
async def test_no_relayed_key_names_an_unvalidated_value(index: int) -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=200, json=_real_cases()))

    # Act
    case = (await _cases(handler=handler))[index]

    # Assert
    dumped = case.model_dump(mode="json")
    assert forbidden_keys(dumped) == []
    assert "provenance" not in (dumped["evidence"]["independentReference"] or {})


async def test_san_marcos_keeps_its_signatures_policy_comparator_context_and_lens() -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=200, json=_real_cases()))

    # Act
    evidence = (await _cases(handler=handler))[5].evidence

    # Assert
    signatures = evidence.radar_signatures or {}
    assert (
        signatures["dual_darkening"].signature_cells,
        signatures["dual_darkening"].supported_cells,
    ) == (
        410,
        4096,
    )
    assert (evidence.signature_policy or {})["co_pol_brightening_min_change_db"] == 3.0
    assert evidence.radar_comparator == "Target minus median of the prior measured dates"
    assert evidence.regional_context is not None
    assert evidence.regional_context.source == "IDEAM hydrological bulletin 853"
    assert evidence.lens_id == "flood_wetland"


@pytest.mark.parametrize(
    argnames=("section", "key"),
    argvalues=[
        ("threshold_policy", "flooded_area_km2"),
        ("threshold_policy", "affected_area_ha"),
        ("independent_reference", "los_displacement_mm"),
        ("independent_reference", "inundation_extent"),
        ("threshold_policy", "flood_probabilities"),
        ("threshold_policy", "cause"),
        ("threshold_policy", "hectares"),
    ],
)
async def test_a_nested_unvalidated_key_in_free_json_is_dropped(section: str, key: str) -> None:
    # Arrange
    raw = _real_cases()
    raw[1]["evidence"][section][key] = 12.5
    handler = Recorder(answer=httpx.Response(status_code=200, json=raw))

    # Act
    evidence = (await _cases(handler=handler))[1].evidence

    # Assert
    kept = getattr(evidence, section) or {}
    assert key not in kept
    assert kept  # the rest of the section is still relayed


async def test_comparison_and_pair_relay_only_their_allow_listed_keys() -> None:
    # Arrange
    raw = _real_cases()
    raw[1]["evidence"]["comparison"]["affected_area_ha"] = 12.5
    raw[3]["evidence"]["pair"]["unwrapped_offset"] = 1.0
    handler = Recorder(answer=httpx.Response(status_code=200, json=raw))

    # Act
    cases = await _cases(handler=handler)

    # Assert
    comparison = cases[1].model_dump(mode="json")["evidence"]["comparison"]
    pair = cases[3].model_dump(mode="json")["evidence"]["pair"]
    assert "affectedAreaHa" not in comparison
    assert "affected_area_ha" not in comparison
    assert comparison["scoredPixels"] == 8775
    assert comparison["lastBaselineSensitivity"]["truePositiveProxyPixels"] == 235
    assert "unwrappedOffset" not in pair
    assert pair["intervalDays"] == 24


async def test_case_layers_carry_a_title_and_kind_and_views_keep_theirs() -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=200, json=_real_cases()))

    # Act
    san_marcos = (await _cases(handler=handler))[5]

    # Assert
    layers = {layer.id: layer for layer in san_marcos.layers}
    change = layers["display_baseline_change_HH"]
    assert (change.title, change.kind) == ("baseline change HH", "change")
    assert layers["display_2026-08-28_HH"].kind == "observed"
    assert san_marcos.visualizations[0].title == "Polarization RGB · HH/HV"


async def test_case_visualizations_use_the_exploration_dto_plus_a_url() -> None:
    # Arrange
    handler = Recorder(answer=httpx.Response(status_code=200, json=_real_cases()))

    # Act
    view = (await _cases(handler=handler))[5].visualizations[0]

    # Assert
    dumped = view.model_dump(mode="json")
    assert isinstance(view, RadarVisualization)
    assert (dumped["png"], dumped["cog"]) == (
        "view_polarization_rgb_hh_hv.png",
        "view_polarization_rgb_hh_hv.tif",
    )
    assert dumped["grid"]["posting_m"] == [10.0, 10.0]
    assert dumped["dates"] == ["2026-10-15"]
    assert dumped["url"] == f"{BASE_URL}/v2/cases/san-marcos/layers/view_polarization_rgb_hh_hv.png"


@pytest.mark.parametrize(argnames="limitations", argvalues=[[], None], ids=["empty", "missing"])
async def test_a_case_without_limitations_gets_the_generic_ones(
    limitations: list[str] | None,
) -> None:
    # Arrange
    raw = _real_cases()
    raw[0]["evidence"]["limitations"] = limitations
    handler = Recorder(answer=httpx.Response(status_code=200, json=raw))

    # Act
    case = (await _cases(handler=handler))[0]

    # Assert
    assert case.limitations == list(CASE_FALLBACK_LIMITATIONS)


async def test_a_case_whose_layer_lives_on_another_host_is_skipped() -> None:
    # Arrange
    raw = _real_cases()
    raw[0]["layers"][0]["png_url"] = "https://elsewhere.example.test/x.png"
    handler = Recorder(answer=httpx.Response(status_code=200, json=raw))

    # Act
    cases = await _cases(handler=handler)

    # Assert
    assert [case.id for case in cases] == CASE_IDS[1:]


@pytest.mark.parametrize(
    argnames="answer",
    argvalues=[
        httpx.Response(status_code=503, json={"detail": "down"}),
        httpx.Response(status_code=200, content=b"<html>"),
        httpx.Response(status_code=200, json={"cases": []}),
        httpx.Response(status_code=200, json=[{"id": "broken"}]),
        httpx.ConnectError("refused"),
    ],
    ids=["outage", "not-json", "not-a-list", "nothing-valid", "unreachable"],
)
async def test_an_unusable_answer_means_the_cases_are_unavailable(
    answer: httpx.Response | Exception,
) -> None:
    # Arrange
    handler = Recorder(answer=answer)

    # Act / Assert
    with pytest.raises(CasesUnavailableError):
        await _cases(handler=handler)


# Real series from the production gateway, read 2026-11-16: a GCOV case and a GUNW case.
GCOV_SERIES = Path(__file__).parents[3] / "fixtures" / "ml_gateway_case_series_gcov.json"
GUNW_SERIES = Path(__file__).parents[3] / "fixtures" / "ml_gateway_case_series_gunw.json"


async def _series(handler: Recorder, case_id: str):
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        return await GatewayCaseCatalog(client=client, base_url=BASE_URL).series(case_id=case_id)


async def test_a_gcov_series_relays_every_date_at_the_point_the_groups_and_the_band() -> None:
    # Arrange
    body = json.loads(GCOV_SERIES.read_text(encoding="utf-8"))
    recorder = Recorder(httpx.Response(status_code=200, json=body))

    # Act
    series = await _series(recorder, case_id="qadirabad")

    # Assert
    assert str(recorder.requests[0].url) == f"{BASE_URL}/v2/cases/qadirabad/series"
    assert len(series.observations) == len(body["observations"])
    first, sent = series.observations[0], body["observations"][0]
    assert (first.date.isoformat(), first.polarization) == (sent["date"], sent["polarization"])
    assert first.gamma0_db == pytest.approx(sent["gamma0_db"])
    assert first.granule == sent["source"].get("granule", sent["source"]["title"])
    assert len(series.observed_groups) == len(body["observed_groups"])
    assert [row.outside_cells for row in series.diagnostic_band_timeline] == [
        row["outside_cells"] for row in body["diagnostic_band_timeline"]
    ]
    assert series.point_readout is not None
    assert series.window_readout is not None
    assert series.intervals == []
    dumped = series.model_dump(by_alias=True, mode="json")
    assert {"diagnosticBandTimeline", "observedGroups", "pointReadout"} <= set(dumped)
    assert dumped["observations"][0]["gamma0Db"] == pytest.approx(sent["gamma0_db"])
    assert forbidden_keys(dumped) == []


async def test_a_gunw_series_relays_its_pair_intervals_without_displacement() -> None:
    # Arrange
    body = json.loads(GUNW_SERIES.read_text(encoding="utf-8"))
    recorder = Recorder(httpx.Response(status_code=200, json=body))

    # Act
    series = await _series(recorder, case_id="kumamoto")

    # Assert
    assert [
        (row.reference_date.isoformat(), row.secondary_date.isoformat(), row.interval_days)
        for row in series.intervals
    ] == [
        (row["reference_date"], row["secondary_date"], row["interval_days"])
        for row in body["intervals"]
    ]
    assert series.observations == []
    assert forbidden_keys(series.model_dump(by_alias=True, mode="json")) == []


@pytest.mark.parametrize(
    argnames="answer",
    argvalues=[
        httpx.Response(status_code=404, json={"code": "not_found"}),
        httpx.Response(status_code=200, json=["not", "a", "series"]),
        httpx.Response(status_code=200, json={"observations": [{"date": "not a date"}]}),
        httpx.ConnectError("down"),
    ],
    ids=["missing", "not an object", "malformed rows", "unreachable"],
)
async def test_a_series_the_gateway_cannot_give_is_unavailable(answer: object) -> None:
    # Act / Assert
    with pytest.raises(CaseSeriesUnavailableError):
        await _series(Recorder(answer), case_id="qadirabad")  # type: ignore[arg-type]
