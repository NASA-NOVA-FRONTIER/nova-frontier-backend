<div align="center">

<img src=".github/assets/hero.jpg" alt="The NISAR Hazard Watch web app that this API serves: its landing page, with the headline &quot;Earth, without the clouds.&quot; over a 3D Earth and the Open the explorer and The Chenab flood buttons" width="100%">

# NISAR Hazard Watch — Backend

**The API behind the radar evidence explorer.**

A FastAPI service that plans which NISAR L-band scenes to read from the public ASF catalog, runs the
analysis on the ML gateway on Modal and serves each result with its layers and its limitations.
Results are diagnostic evidence: no forecasts, no probabilities, no causes.

[![API docs](https://img.shields.io/badge/api%20docs-swagger%20ui-c9b48b?style=for-the-badge&labelColor=04070e)](https://nova-frontier-backend-main.up.railway.app/docs)
[![Live app](https://img.shields.io/badge/live%20app-open%20the%20explorer-c9b48b?style=for-the-badge&labelColor=04070e)](https://nova-frontier-frontend.vercel.app)

[![CI](https://github.com/NASA-NOVA-FRONTIER/nova-frontier-backend/actions/workflows/ci.yml/badge.svg)](https://github.com/NASA-NOVA-FRONTIER/nova-frontier-backend/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.13-3776ab?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![uv](https://img.shields.io/badge/uv-locked-de5fe9?logo=uv&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-17-4169e1?logo=postgresql&logoColor=white)
![Railway](https://img.shields.io/badge/Railway-deployed-0b0d0e?logo=railway&logoColor=white)
![Modal](https://img.shields.io/badge/Modal-ML%20gateway-7fee64)
![NASA Space Apps 2026](https://img.shields.io/badge/NASA%20Space%20Apps-2026-0b3d91)

**[Frontend](https://github.com/NASA-NOVA-FRONTIER/nova-frontier-frontend)** ·
**[Model](https://github.com/NASA-NOVA-FRONTIER/nova-frontier-model)** ·
**[Live demo](https://nova-frontier-frontend.vercel.app)**

</div>

For a point or a drawn area it plans the scenes to read from the public ASF catalog, sends that plan to the ML gateway on Modal (`nova-frontier-model`), tracks the job and serves the result with its layers, `limitations` and `scientificStatus: "diagnostic"`. It also lists the cases measured ahead of time, the NISAR interferometric pairs over a point, the lenses and place search results for the globe. A `wildfire` answer adds NASA FIRMS active-fire detections as separate context.

| Method | Path (under `/api/v1`) | Answers |
|---|---|---|
| `POST`, `GET`, `DELETE` | `/explorations`, `/explorations/{id}` | Start, follow or cancel an exploration of an area with one lens |
| `POST` | `/explorations/{id}/analysis` | Start or reuse a regional analysis of the exploration's scene series |
| `GET` | `/explorations/{id}/layers/{layerId}`, `/explorations/{id}/assets/{name}` | Redirect to a layer image or a published file of the job |
| `GET` | `/coverage` | Which scenes would be read for a point, without running anything |
| `GET` | `/cases`, `/cases/{id}`, `/cases/{id}/series`, `/cases/{id}/layers/{layerId}` | The known cases measured ahead of time, one case's evidence, its measured series, its layer images |
| `GET` | `/insar/pairs` | NISAR L-band interferometric pairs over a point, newest first |
| `GET` | `/lenses` | The lenses, what each one shows and how many dates it needs |
| `GET` | `/places` | Place search for the globe |
| `GET`, `POST` | `/assistant` | Whether Nova answers with Claude; Nova's answer about the result on screen, streamed as server-sent events |
| `GET` | `/health`, `/health/live` | Dependency report and liveness check |

Details of each endpoint are in [API](#api).

## Contents

- [Architecture](#architecture)
- [Quickstart](#quickstart)
- [Configuration](#configuration)
- [API](#api)
- [Example requests](#example-requests)
- [Project layout](#project-layout)
- [Architecture decisions](#architecture-decisions)
- [Scene planning (SAR core)](#scene-planning-sar-core)
- [Exploration flow](#exploration-flow)
- [What we don't claim](#what-we-dont-claim)
- [Data sources and citations](#data-sources-and-citations)
- [Testing](#testing) · [Quality](#quality) · [CI](#ci) · [Deployment](#deployment)
- [NASA Space Apps 2026](#nasa-space-apps-2026)
- [How to cite this project](#how-to-cite-this-project)
- [License](#license)

## Architecture

How a question travels: the browser calls this backend on Railway, which plans the scenes and hands the job to the ML gateway on Modal; the gateway reads NISAR data from NASA archives and the radar layers go back to the globe.

<img src=".github/assets/architecture.png" alt="NISAR Hazard Watch, how a question travels: the browser calls this backend on Railway, which plans scenes from ASF, adds FIRMS fire detections and Nominatim places, keeps jobs in PostgreSQL and posts the job to the ML gateway on Modal; the gateway reads NISAR data from NASA and the radar layers go back to the globe" width="100%">

<sub>Diagram source: the frontend repo, <code>docs/architecture/</code> (render with <code>pnpm diagram</code>).</sub>

## Quickstart

```bash
uv sync                                  # Python 3.13 + locked dependencies
cp .env.example .env
docker compose up -d db                  # PostgreSQL 17 on localhost:5432
uv run alembic upgrade head
uv run uvicorn nisar_hazard_watch.main:app --reload
curl localhost:8000/api/v1/health
```

Or run everything in containers with `docker compose up --build` (applies the migrations, then serves on `:8000`). Interactive docs live at `/docs`.

## Configuration

Environment variables (see `.env.example`). The app fails at start-up on a malformed value instead of running misconfigured: origins, timeouts and the log level are validated, and `ENVIRONMENT=production` refuses to start without an explicit `DATABASE_URL`. `DATABASE_URL` accepts the plain `postgresql://` form that Railway provides and adds the asyncpg driver itself.

| Variable | Default | Meaning |
|---|---|---|
| `ENVIRONMENT` | `local` | `local`, `test` or `production` |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL` (any case); JSON logs on stdout |
| `DATABASE_URL` | local Postgres | SQLAlchemy URL of the application database (required in production, never printed) |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` | Comma-separated list or JSON array of origins such as `https://app.example.com` (scheme and host, no path, no trailing slash, at least one) |
| `CMR_HEALTH_URL` | NASA CMR health | Endpoint probed by `/api/v1/health` |
| `CMR_HEALTH_TIMEOUT_SECONDS` | `5` | Per-phase HTTP timeout of the CMR probe (> 0) |
| `DATABASE_HEALTH_TIMEOUT_SECONDS` | `3` | Total deadline of the database probe (> 0) |
| `HEALTH_PROBE_TIMEOUT_SECONDS` | `10` | Total deadline of any probe; a slower one is reported as down (> 0) |
| `ML_GATEWAY_URL` | `https://japv-x2612--nova-frontier-model.us-east.modal.run` | Modal gateway that runs the analysis of a scene plan (the production app `nova-frontier-model`, deployed from `main` of `nova-frontier-model`) |
| `RUNNER` | `gateway` | `gateway`, or `inProcess` (synthetic results labelled as demo; refused in production) |
| `MAX_ACTIVE_EXPLORATIONS` | `5` | Explorations running at once; more get `503 QUEUE_FULL` |
| `EXPLORATION_DEADLINE_SECONDS` | `480` | A running exploration becomes `partial` with `TIMEOUT_PARTIAL` after this deadline. The production worker has up to 420 s plus gateway admission and startup. Cache hits can return immediately. |
| `EXPLORATION_CACHE_TTL_SECONDS` | `86400` | A finished exploration with the same lens, area and scenes is reused for this long |
| `RATE_LIMIT_PER_MINUTE` | `20` | Requests per client to the exploration and coverage endpoints |
| `DAILY_LIMIT_CLIENT`, `DAILY_LIMIT_APP` | `20`, `250` | New analyses a day (UTC) per client and for the whole app. Cache hits never count; the app limit stays under the 300 jobs a day the ML gateway admits. `GET /api/v1/limits` shows what is left |
| `GATEWAY_SHARED_SECRET` | unset | Bearer token sent on every job submission to the ML gateway (`Authorization: Bearer ...`). Never logged or returned. Set it in Railway and in the gateway's Modal Secret before the gateway starts requiring it |
| `TRUSTED_PROXY_HOPS` | `2` | Entries the proxies in front of the API append to `X-Forwarded-For` (measured on Railway's edge: 2; with 1 every request landed in a different bucket and the limit never fired; recount if another proxy such as a Vercel rewrite is added). The client is that many entries from the right, so a spoofed leading address cannot dodge the limit; `0` ignores the header and uses the socket peer |
| `ETA_PRIOR_SECONDS` | `140` | ETA until three comparable runs exist; then the p80 of the last 50 |
| `ASF_TIMEOUT_SECONDS`, `GATEWAY_TIMEOUT_SECONDS` | `30`, `20` | HTTP timeouts towards the ASF catalog and the ML gateway (> 0) |
| `GEOCODER_URL`, `GEOCODER_TIMEOUT_SECONDS` | Nominatim `/search`, `8` | Place search provider (only this host is ever called; never taken from a request) and its timeout (> 0) |
| `PRECOMPUTED_CASES_PATH` | unset | JSON list of precomputed cases offered when the catalog is down |
| `EARTHDATA_TOKEN` | unset | Reported as configured or not (blank counts as missing); never logged or returned |
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | unset | Both are needed to count as configured; never logged or returned |
| `FIRMS_MAP_KEY` | unset | Free NASA FIRMS key for the wildfire lens' independent fire context; without it the wildfire answer says `notConfigured` and stays radar-only. It travels in the FIRMS URL path, so `httpx` request logging is silenced; never logged or returned |
| `FIRMS_URL` | `https://firms.modaps.eosdis.nasa.gov` | FIRMS base URL |
| `FIRMS_TIMEOUT_SECONDS`, `FIRE_CONTEXT_TIMEOUT_SECONDS` | `10`, `15` | Per-request timeout and total budget of the fire context lookup (> 0); a slower lookup is reported as `unavailable`, never as an error |
| `ANTHROPIC_API_KEY` | unset | Claude key for Nova's answers (`POST /api/v1/assistant`). Without it the endpoint answers `503 ASSISTANT_UNAVAILABLE` and the chat keeps its rule-based answers. A Railway variable only; never logged or returned |
| `ASSISTANT_MODEL` | `claude-opus-5-5` | The Claude model behind Nova. Server-side fallback on a declined answer is sent only for models that accept it |
| `ASSISTANT_RATE_LIMIT_PER_MINUTE`, `ASSISTANT_DAILY_TOKEN_LIMIT` | `6`, `1000000` | Questions per client per minute, and the tokens (in and out) all clients may use per UTC day; above it the endpoint answers `429 ASSISTANT_BUDGET_EXHAUSTED` until 00:00 UTC |

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/health` | Dependency report: database (critical), NASA CMR, Modal and Earthdata credentials. `200` when ok or degraded, `503` when a critical dependency is down |
| `GET /api/v1/health/live` | Liveness only; never touches a dependency (used by the Railway health check) |
| `POST /api/v1/explorations` | Start an exploration `{lens, geometry, source?, opticalEvidence?, pairId?, coherenceThreshold?, startDate?, endDate?, direction?, seriesKey?}` (`startDate`/`endDate` choose the window: both or neither, 36 to 365 days, ending no later than today, refused for `insar`; without them, the last 152 days) (`direction` `A` or `D` and `seriesKey`, from coverage `series[]`, limit the planner to matching series; refused for `insar`, whose pair sets them, and a 422 when they disagree; nothing matching is the usual `NO_COVERAGE` answer; without them the planner picks one itself) (`pairId` is required by the `insar` lens and refused by the others; `coherenceThreshold` is 0.1 to 0.9, default 0.35) (`geometry` is a GeoJSON Point, Polygon or MultiPolygon). `202` while it runs, `200` when the answer is final (cache hit, or no data) |
| `GET /api/v1/explorations/{id}` | Status, stage, per-stage seconds, `etaSeconds` and `etaRemainingSeconds`, progress, `queuePosition`, the scene plan and, when done, the result with its layers, limitations and `scientificStatus`. Each `result.observations[]` carries the date, status, reason, granule, `point_db` (HH/HV dB at the point, null when masked), valid pixels per channel and the product `quality`; `result.lens` is relayed as the gateway sends it (including `temporal_analysis`); `result.quality` adds `observedDateCount`, `usableWindowDateCount` and `seriesAttempts`; each `result.products.visualizations[]` (id, recipe, title, dates, interpretation, components, supported and total cells, bounds) carries a `url` through this API |
| `POST /api/v1/explorations/{id}/analysis` | Start or reuse a bounded regional analysis of the exploration's catalog series. Poll the returned exploration ID. Regional measurements carry their own sampled dates and grid in `result.products.analysis`. |
| `DELETE /api/v1/explorations/{id}` | Cancel a running exploration |
| `GET /api/v1/explorations/{id}/layers/{layerId}` | `307` redirect to the layer image on the ML gateway |
| `GET /api/v1/explorations/{id}/assets/{name}` | `307` redirect to a published artifact from this job. The result includes its media type, size and SHA-256. |
| `GET /api/v1/places?q=&limit=` | Place search for the globe (OpenStreetMap Nominatim behind a 24 h cache and a one-request-per-second throttle, as its policy asks; send it on submit, never per keystroke). Answers `places[]` with `point`, `bbox` and `attribution` |
| `GET /api/v1/lenses` | The supported lenses and how many dates they need |
| `GET /api/v1/limits` | What is left of today's new analyses: `remainingApp`, `remainingClient`, `resetsAt` (UTC) and the limits themselves. A `429` from the exploration endpoints carries `Retry-After` |
| `GET /api/v1/insar/pairs?lon=&lat=&startDate=&endDate=` | NISAR L-band interferometric (GUNW) pairs over a point, newest first, listed from the public catalog through the ML gateway (default window: the last 180 days, at most 366). Rate-limited like explorations |
| `GET /api/v1/coverage?lon=&lat=[&lens=&opticalEvidence=&startDate=&endDate=&direction=&seriesKey=]` | The scene plan for a point without running anything: the five chosen `plan.dates`, the window read (`plan.windowStart`, `plan.windowEnd`), every pass of the series in it (`passes[]`), every series found there (`series[]`: `seriesKey`, `direction`, `track`, `frame`, `code`, `mode`, measured `dates`, `coverage`, `dualPol`; the planner's default first, the list never narrowed by a choice), and for `lens` the `etaSeconds`, `cache` state and, from a cached run, the `grid`. `direction`/`seriesKey` plan that series, as an exploration would |
| `GET /api/v1/assistant` | `{available, model}`: whether a key is set and today's budget is left, so the chat labels its answers before anyone asks |
| `POST /api/v1/assistant` | Nova's answer `{message, history[], context}` (`context` is the frontend's summary of the result on screen, read by the model as data, never as instructions). Streams `text/event-stream`: `delta` events with text, then `done` or `error` (`ASSISTANT_DECLINED`, `UPSTREAM_ASSISTANT_ERROR`). Refused before streaming with `503 ASSISTANT_UNAVAILABLE` (no key), `429 RATE_LIMITED` or `429 ASSISTANT_BUDGET_EXHAUSTED`. The system prompt forbids causes, probabilities, hectares, displacement and invented numbers |
| `GET /api/v1/cases` | The five demo cases measured ahead of time on the ML gateway (`/v2/cases`), one per phenomenon (`DEMO_CASE_IDS`: qadirabad, choco, bug-fire, para-event-02, niscemi-aftermath; frontend issue #28), in its order: id, title, point, status and the baseline and assessment dates. Every other gateway case still opens by id. Kept in memory for 10 minutes and refreshed in the background, so a copy is served at once; after a gateway failure it is not called again for 60 s. With no copy the answer is `502 CASES_UNAVAILABLE`. Known `status` values: `partial`, `complete`, `not_displacement_ready`, `evaluated`. Rate-limited |
| `GET /api/v1/cases/{id}` | One case: grid, series key, allow-listed evidence (cell counts, threshold policy, optical comparison, sources, pair, common support, radar signatures and their policy, radar comparator, regional context and lens; never area, hectares, probability, depth, displacement or cause), layers (with `title` and `kind`), visualizations, `limitations`, `scientificStatus` and `isDemo`. Unknown id: `404 CASE_NOT_FOUND`. Rate-limited |
| `GET /api/v1/cases/{id}/series` | The case's measured series from the gateway (`/v2/cases/{id}/series`). GCOV cases: `observations` (marker pixel, `gamma0Db` per date and channel, `granule`), `observedGroups` (median and spatial IQR of each cell group per date and channel), `diagnosticBandTimeline` (`outsideCells` of `eligibleCells` per assessment date), `targetDate`. GUNW cases: `intervals` (reference and secondary dates, days, median coherence, supported cells). Both: `pointReadout` and `windowReadout` (the gateway's `area_readout`, renamed because no key naming an area is relayed), scrubbed like the evidence. Kept 10 minutes per case. Unknown id: `404 CASE_NOT_FOUND`; gateway failure: `502 CASES_UNAVAILABLE`. Rate-limited |
| `GET /api/v1/cases/{id}/layers/{layerId}` | `307` redirect to the layer or visualization image on the ML gateway |

Every response carries `X-Request-ID` (a safe incoming value is kept, otherwise one is generated), including unexpected 500s, which also keep their CORS headers. Errors are `application/problem+json` (server-side details are never echoed, and the headers of an `HTTPException` such as `Allow` or `Retry-After` are preserved):

```json
{ "type": "about:blank", "title": "Not Found", "status": 404, "detail": "Not Found",
  "reasonCode": "NOT_FOUND", "requestId": "bd343cf307d144609d84178020e7ffd2" }
```

Payload fields are camelCase.

## Example requests

Read-only calls against the public deployment (responses captured on 2026-11-15, trimmed).

```bash
curl -s https://nova-frontier-backend-main.up.railway.app/api/v1/lenses
```

```json
[
  {
    "id": "flood_wetland",
    "title": "Flood and wetland",
    "description": "Dual-polarization darkening and brightening of the latest scene against the area's own earlier measurements, diagnostic of open-water and wet-surface change.",
    "opticalEvidence": true,
    "minimumDates": 4
  },
  …
  {
    "id": "insar",
    "title": "Ground motion (InSAR pair)",
    "opticalEvidence": false,
    "minimumDates": 2,
    …
  }
]
```

The scene plan for Qadirabad (Chenab river, Pakistan), without running anything:

```bash
curl -s "https://nova-frontier-backend-main.up.railway.app/api/v1/coverage?lon=73.713&lat=32.329"
```

```json
{
  "plan": {
    "status": "ready",
    "seriesKey": "084_A_018_4005_DHDH",
    "dates": ["2026-07-14", "2026-08-19", "2026-09-12", "2026-10-18", "2026-11-11"],
    "maturityMixed": true,
    "notes": []
  },
  "areaKm2": 104.904,
  "warnings": [],
  "precomputedCase": null
}
```

## Project layout

```
src/nisar_hazard_watch/
  api/          app factory, composition root, middlewares (request id, unexpected errors), error handlers, routes/<resource>/
  services/     use cases: HealthService, ScenePlanner (and scene_selection), ExplorationService, EtaEstimator, CaseService, PlaceSearchService, lens_catalog
  hazards/      per-hazard logic: wildfire/ (FIRMS fire context, assessment window), earthquake/ (InSAR pairs service)
  ports/        interfaces the services depend on (DependencyProbe, SarCatalog, AnalysisRunner, JobRepository, PrecomputedCases, CaseCatalog, InsarPairCatalog, Geocoder, FireContextProvider, FireDetectionSource)
  adapters/     implementations: db/ (jobs), nasa/ (CMR health), asf/ (scene catalog), geocoding/ (Nominatim), runners/ (ML gateway, in-process), gateway/ (known cases, InSAR pairs), firms/ (active-fire detections), cases/, credentials/
  models/       camelCase DTOs (CamelModel), problem details, health
  constants/    routes, headers, reason codes, enums: no magic strings
  config/       settings (pydantic-settings)
  exceptions/   AppError and subclasses
  utils/        logging, request context, database url, timing, geometry (areas of interest), rate limiter, TTL cache, throttle, gateway layers, GUNW names
migrations/     Alembic (async): 0001 baseline, 0002 explorations
tests/          unit/ (mirrors src), integration/ (Postgres), live/ (NASA)
```

### Adding an endpoint group

1. Add the path and reason codes to `constants/`.
2. Create `api/routes/<resource>/routes.py` exporting a `router`.
3. Append `(router, "/<resource>")` to `ROUTERS` in `api/routes/router.py`.
4. Put logic in `services/`, depend on a `ports/` interface and implement it in `adapters/`.
5. Write DTOs as `CamelModel` subclasses and the tests mirroring the source path.

## Architecture decisions

- **Hexagonal: ports and adapters.** Services depend on `Protocol` interfaces in `ports/`; concrete adapters are wired only in `api/composition.py`. That is how `RUNNER=inProcess` swaps the ML gateway for a synthetic, demo-labelled runner, and how the unit tests run on fakes with no network.
- **Heavy reads on Modal, a small API on Railway.** Reading the planned NISAR windows is the slow part (stage budgets in `constants/explorations.py`: 105 s reading against 15 s analysing and 15 s rendering), so it runs on the `nova-frontier-model` gateway's workers, which keep a chip cache on a Modal Volume. The API only plans, queues and relays, and refuses new work with `503 QUEUE_FULL` when `MAX_ACTIVE_EXPLORATIONS` are running or the gateway is busy.
- **Asynchronous jobs with polling.** An exploration takes minutes, so `POST` answers `202` with a job and the client polls `GET /explorations/{id}`, which refreshes the job from the gateway; `etaSeconds` comes from the p80 of recent comparable runs (`EtaEstimator`).
- **PostgreSQL as the job store and a 24 h result cache.** Jobs live in the database, not in memory, so any poll sees the same state. `transition` only updates rows that are still active, so a cancel and a late poll cannot overwrite each other. A finished job with the same lens, area and granules is reused for `EXPLORATION_CACHE_TTL_SECONDS` (86,400 s).
- **One error shape.** Every error is `application/problem+json` with a stable `reasonCode` and the `requestId`; the frontend maps the code to its own message, and server-side details of a 500 are never echoed.

## Scene planning (SAR core)

`ScenePlanner` turns an area of interest and "now" into the exact scenes to read.

| # | Step | Rule | Why |
|---|---|---|---|
| 1 | Area | A point becomes the 10.24 km square in the local UTM zone (`aoi_from_point`). A drawn polygon (`aoi_from_geojson`) needs a closed ring and at most 100 vertices; it is repaired with `buffer(0)`, split at ±180° and measured on the ellipsoid | One fixed square gives every point the same 1024 × 1024 window at 10 m; repairing and splitting keeps hand-drawn and dateline shapes valid |
| 2 | Size limit | Capped by native pixels: about 110 km² is the ideal, 400 km² the hard limit (`AREA_TOO_LARGE`) | The analysis reads a window of native pixels, so the cost grows with the area |
| 3 | Catalog query | One ASF SearchAPI query for the last five months (152 days), or for the whole days of the user's range, with no maturity or configuration filter; maturity is read from the product URL | Seeing every product lets the planner choose; the query fails loudly instead of returning a truncated list |
| 4 | One scene per acquisition | VALIDATED over PROVISIONAL over BETA over urgent response, then CRID and version | The same pass can be published several times; keep the most mature copy |
| 5 | One series | Group by the ML service's key `track_direction_frame_bandwidthCode_mode`; prefer full coverage (≥ 95 %), dual-pol, most dates, newest; a client's `direction` or `seriesKey` limits the candidates first | A frame can mix 2005 and 4005 bandwidth codes or DHDH and QPDH modes, whose grids are incompatible |
| 6 | Dates | Default window: walk back from the newest scene in steps of about 30 days (± 6), up to five images. A user's range (`startDate`/`endDate`): the scene nearest each of five evenly spaced targets from start to end, kept once if two targets share it (the earlier on a tie); a top-up to four comes from passes inside the range | Evenly spaced dates give the lens a baseline and a target |
| 7 | Verdict on the plan | Fewer than four usable dates is `insufficientHistory`, no scene at all is `noCoverage`; `maturityMixed` tells the UI when the series mixes maturities | The lenses need at least three earlier dates plus the target; the UI must say when maturities differ |

## Exploration flow

`POST /api/v1/explorations` validates the area, refuses `source: "S"` (S-band will arrive as a precomputed layer), plans the scenes, answers from the cache when the same lens, area and granules finished in the last day, checks capacity, hands the plan to the runner and stores the job. The default runner posts it to the Modal gateway of `nova-frontier-model`, which reads the planned windows (up to 10.24 km at 10 m), runs the lens and serves the layers; polling `GET /explorations/{id}` refreshes the job from the gateway.

**States** (`ExplorationStatus`):

- `queued` → the job was handed to the gateway and waits there (also the state the gateway reports while it queues).
- `running` → the gateway reports the job is processing.
- `succeeded` → the gateway answered `complete`.
- `partial` → the gateway answered `partial`, or `complete` with a lens that had `insufficient_data`, or the deadline (`EXPLORATION_DEADLINE_SECONDS`) passed while the job was still active (`TIMEOUT_PARTIAL`).
- `noData` → the plan had no usable scenes (`NO_COVERAGE` or `INSUFFICIENT_HISTORY`, final at once), or the gateway found no usable measurements (`NO_COVERAGE`).
- `failed` → the gateway reported a failure, an unknown status or an empty result (`ANALYSIS_FAILED`).
- `cancelled` → `DELETE /explorations/{id}` on an active job (`CANCELLED`).

**While it runs** (the waiting panel's four steps: searching the catalog → reading passes → measuring change → drawing layers):

- `stages` starts with `planning` (searching the catalog, done before the job is handed over). While the job is active, one `processing` entry stands for the other three steps, because the gateway reports only `queued` or `running`, with no sub-stage. Once it ends, `reading`, `analysing` and `rendering` arrive with their seconds.
- `progress.scenesRead` is null until the result arrives, for the same reason; `scenesTotal` is known from the plan.
- `queuePosition` is how many analyses are ahead of this one: while `queued`, the other queued jobs created before it (ties broken by id); 0 while `running`; null once it ends. Running jobs don't count, because the gateway runs several at once and also reports `queued` while a worker starts. Another job's status is only refreshed when someone polls it, so an abandoned queued job counts as ahead until its deadline.

**Reason codes** (`constants/errors.py`). Errors are `application/problem+json`; the codes marked "in the job" arrive inside a `200` exploration as `error.reasonCode`.

| `reasonCode` | HTTP | What the user sees |
|---|---|---|
| `INVALID_REQUEST` | 422 | The request body or query did not validate (also a bad InSAR pair, or a `direction` and `seriesKey` that disagree) |
| `INVALID_GEOMETRY` | 422 | The drawn area is not a valid Point, Polygon or MultiPolygon |
| `AREA_TOO_LARGE` | 422 | The area is above the 400 km² limit |
| `SOURCE_NOT_AVAILABLE` | 422 | S-band was asked for; only L-band runs on demand |
| `INVALID_QUERY` | 422 | The place search text is too short or too long |
| `INVALID_DATE_RANGE` | 422 | `startDate`/`endDate`: only one sent, end before start, end after today, a span outside 36 to 365 days, or dates with the `insar` lens |
| `NOT_FOUND` | 404 | Unknown path or exploration |
| `CASE_NOT_FOUND` | 404 | Unknown case id |
| `METHOD_NOT_ALLOWED` | 405 | Wrong method for the path |
| `PAYLOAD_TOO_LARGE` | 413 | The request body is too large |
| `RATE_LIMITED` | 429 | More than `RATE_LIMIT_PER_MINUTE` requests from one client; `Retry-After` says when to retry |
| `DAILY_LIMIT_REACHED` | 429 | The client, or the whole app, used today's new analyses (`DAILY_LIMIT_CLIENT`, `DAILY_LIMIT_APP`); `Retry-After` is the time to the 00:00 UTC reset |
| `UPSTREAM_CATALOG_ERROR` | 502 | The ASF catalog failed; names a precomputed case when one matches |
| `UPSTREAM_ML_ERROR` | 502 | The ML gateway did not answer |
| `UPSTREAM_GEOCODER_ERROR` | 502 | Place search provider failed |
| `CASES_UNAVAILABLE` | 502 | No copy of the known cases and the gateway failed |
| `QUEUE_FULL` | 503 | `MAX_ACTIVE_EXPLORATIONS` are running; retry later |
| `INTERNAL_ERROR` | 500 | Unexpected error; details are never echoed |
| `NO_COVERAGE` | in the job | `noData`: no scene covers the area (or none in the `direction`/`seriesKey` asked for), or no usable measurement |
| `INSUFFICIENT_HISTORY` | in the job | `noData`: fewer than four usable dates |
| `TIMEOUT_PARTIAL` | in the job | `partial`: the deadline passed; the planned scenes are listed |
| `ANALYSIS_FAILED` | in the job | `failed`, with a plain detail from the gateway's error code |
| `CANCELLED` | in the job | `cancelled` |

**Every result** carries `limitations[]`, `scientificStatus: "diagnostic"` and `isDemo`; an area wider than the analysed window says so in `limitations` and `quality.windowTruncated`.

**Wildfire** answers also carry `result.fireContext`, kept apart from the radar `lens` (it lives in `hazards/wildfire/`): NASA FIRMS VIIRS active-fire detections (SNPP and NOAA-20, archive and near real time, de-duplicated) inside the area between the last baseline pass and the target pass, low-confidence ones counted separately. It is `available`, `unavailable` (FIRMS failed or was slow) or `notConfigured`, and never reports a cause or a burned area.

**InSAR** (`insar` lens) takes a pair chosen from `GET /api/v1/insar/pairs` instead of a GCOV scene plan (the planner is skipped): the backend reads the pair's two days from its granule name, sends `insar-pair` to the gateway and returns `result.insar` (median coherence, coherent and phase cells, coherence and wrapped phase at the point) with two layers, coherence and wrapped phase (cyclic palette). The phase is wrapped and not corrected for troposphere or ionosphere, so `losDisplacementCm` is always `null` and every answer says so.

**Measured timings:**

| Case | Date | Input | Cells / window | Time |
|---|---|---|---|---|
| Kumamoto, InSAR pair (track 24, 2026-07-21 to 2026-08-14) | 2026-11-12 | One GUNW pair | 62,500 coherent cells in the 5 km window; 39,584 with phase at the 0.35 threshold | 50 s |
| Qadirabad, GCOV lens | 2026-11-12 | Five scenes | 1024 × 1024 cells | About 35 s of analysis plus rendering once warm; 47 s from a cold start |

## What we don't claim

| We never report | Why, as the code enforces it |
|---|---|
| Hectares or any burned, flooded or affected area | Every exploration carries the limitation "No forecast, probability, cause, area in hectares or displacement is reported." (`constants/explorations.py`); case evidence keys containing `area`, `hectares`, `km2`, `flooded`, `inundation` and similar words are never relayed (`FORBIDDEN_EVIDENCE_WORDS`) |
| Displacement in cm or mm | The InSAR phase is wrapped and not corrected for troposphere or ionosphere, so `losDisplacementCm` is typed `None` and is always `null` (`models/insar_summary.py`, `INSAR_LIMITATIONS`) |
| Probabilities | Results are `scientificStatus: "diagnostic"` (`SCIENTIFIC_STATUS`): diagnostic evidence from measured backscatter, "not a validated classifier" |
| Causes | The wildfire limitation says a radar change over burnt land "does not establish a fire as the cause"; FIRMS detections are kept apart from the radar verdict and "no burned area is reported" (`constants/fire_context.py`) |
| Forecasts | Every answer compares a measured target pass with earlier measured passes; no field or service predicts a future state, and the limitation says so |

## Data sources and citations

| Product | Provider | Used by | Terms | How to cite |
|---|---|---|---|---|
| NISAR L2 GCOV (`NISAR_L2_GCOV_V1`, `_PROVISIONAL_V1`, `_BETA_V1`, `UR_L2_L_GCOV`) and L2 GUNW | NASA-ISRO NISAR, archived by the ASF DAAC | Scene plan (ASF SearchAPI) and the ML gateway's reads | NASA mission data are CC0 unless a product states otherwise; "there are no restrictions on the use of these data" ([NASA data use guidance](https://www.earthdata.nasa.gov/engage/open-data-services-software-policies/data-use-guidance)) | "NISAR follows NASA's standard Data Use and Citation Guidance" ([ASF NISAR docs](https://nisar-docs.asf.alaska.edu/data-use-citation-guidance/)): cite each dataset in the text and in the reference list, and acknowledge NASA as the source |
| NASA CMR (Common Metadata Repository) | NASA Earthdata | `/api/v1/health` probe; granule search on the ML gateway | As above | As above |
| OPERA DSWx-HLS (`OPERA_L3_DSWX-HLS_V1`) | NASA JPL OPERA, archived by PO.DAAC | The ML gateway's optical evidence (flood lens) | See the [PO.DAAC dataset page](https://podaac.jpl.nasa.gov/dataset/OPERA_L3_DSWX-HLS_V1) | Use the suggested citation on the [PO.DAAC dataset page](https://podaac.jpl.nasa.gov/dataset/OPERA_L3_DSWX-HLS_V1) |
| NASA FIRMS VIIRS 375 m active fires (Suomi NPP and NOAA-20, standard and near real time) | NASA LANCE / ESDIS | Wildfire `fireContext` | Free MAP_KEY; NASA data use guidance applies | "We acknowledge the use of data and/or imagery from NASA's Fire Information for Resource Management System (FIRMS), part of NASA's Land, Atmosphere Near real-time Capability for Earth observations (LANCE) and NASA's Earth Science Data and Information System (ESDIS)." ([Earthdata FIRMS](https://www.earthdata.nasa.gov/learn/find-data/near-real-time/firms)). Algorithm: Schroeder et al. (2014), doi:[10.1016/j.rse.2013.12.008](https://doi.org/10.1016/j.rse.2013.12.008) |
| OpenStreetMap Nominatim | OpenStreetMap Foundation | `GET /api/v1/places` | ODbL ([OSM copyright](https://www.openstreetmap.org/copyright)); [usage policy](https://operations.osmfoundation.org/policies/nominatim/): "an absolute maximum of 1 request per second", an identifying User-Agent, "Results must be cached on your side", no client-side autocomplete | "© OpenStreetMap contributors" (returned as `attribution` in every places answer). The backend keeps the policy: one request per 1.1 s, a User-Agent naming this repository, a 24 h cache, search on submit only |

## Testing

```bash
uv run pytest                                      # unit tests, no network, 80 % coverage gate
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/nisar_hazard_watch \
  uv run pytest -m integration                     # needs a real PostgreSQL
uv run pytest -m live                              # real NASA CMR and ASF catalog, and one exploration on the ML gateway
```

## Quality

```bash
uv run ruff check && uv run ruff format --check && uv run pyright
uv run pre-commit install
```

## CI

`.github/workflows/ci.yml` runs on every pull request and on pushes to `main`: **Checks (lint, types, tests)** (ruff, pyright, pytest with coverage against a PostgreSQL service) and **Docker build**.

## Deployment

Railway builds the `Dockerfile`, runs `alembic upgrade head` before each deploy (`railway.toml`) and health-checks `/api/v1/health/live`. Variables: `DATABASE_URL` (reference of the Postgres service), `CORS_ALLOWED_ORIGINS`, `ENVIRONMENT=production`, `LOG_LEVEL`, `GATEWAY_SHARED_SECRET` (the same value as the gateway's Modal Secret), `DAILY_LIMIT_CLIENT` and `DAILY_LIMIT_APP`. **`main` is production**: change it only through reviewed pull requests with green CI.

## NASA Space Apps 2026

**Challenge:** [Dancing with the SARs](https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/). It asks for an interactive application that uses NISAR radar data to track and show one or more kinds of surface change around the world.

**Demo:** the live app at [nova-frontier-frontend.vercel.app](https://nova-frontier-frontend.vercel.app), backed by this API ([Swagger UI](https://nova-frontier-backend-main.up.railway.app/docs)).

**Team Nova Frontier:**

| Name | Role | Built |
|---|---|---|
| [Jesús Alfonso Pinzón Vega](https://github.com/JAPV-X2612) | Architect · team lead | Backend API and system design |
| [Cristian Santiago Pedraza Rodríguez](https://github.com/cris-eci) | Front end · design | Landing, explorer, method and the design system |
| [Andersson David Sánchez Méndez](https://github.com/AnderssonProgramming) | Software developer | Landslide hazard module (in progress) |
| [David Stiven Sarria Arcila](https://github.com/DASarria) | Data pipeline · wildfires | NISAC_Data_Lab: the ASF data pipeline and the response-time lab |
| [Daniel Felipe Martínez Hernández](https://github.com/Ch0comilo) | Machine learning · radar science | nova-frontier-model and NISAR-Models |
| [Katheryn Sofía Guasca Chavarro](https://github.com/KillerZeus666) | Front-end developer | Flood analysis interface, event timeline and data visualizations |

**Use of AI:** code in this repository was written with help from Claude Code (Anthropic), under the conventions in [`CLAUDE.md`](CLAUDE.md), and reviewed by the team through pull requests. The scientific numbers (cell counts, coherence, timings) come from measured runs of the radar pipeline in [nova-frontier-model](https://github.com/NASA-NOVA-FRONTIER/nova-frontier-model) on real NISAR data, not from an AI model.

**Acknowledgements:** NASA and ISRO for the NISAR mission and its open data; the Alaska Satellite Facility DAAC, which archives and serves the NISAR products; NASA LANCE / ESDIS for FIRMS; NASA JPL OPERA and PO.DAAC; the OpenStreetMap contributors; and the organisers of the NASA Space Apps local event in Chía, Colombia.

## How to cite this project

```text
Nova Frontier (2026). NISAR Hazard Watch — Backend. NASA Space Apps Challenge 2026.
https://github.com/NASA-NOVA-FRONTIER/nova-frontier-backend
```

GitHub's "Cite this repository" button reads [`CITATION.cff`](CITATION.cff). Cite the data products above as well.

## License

Apache-2.0.
