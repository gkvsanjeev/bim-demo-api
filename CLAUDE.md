# CLAUDE.md

This file gives Claude Code context for working on the **iEP SkySAFE 2.0** Python project.

---

## Project overview

This project implements the **iEP processing backend** for CAAS (Civil Aviation Authority of Singapore) SkySAFE 2.0 — the system used by CAAS officers to assess building height consultation applications for aviation safety.

The Python service receives a **CORENET X–compliant IFC+SG BIM file** from SkySAFE (via SFTP + an API trigger), extracts the simplified exterior shell of the proposed building, runs a series of geospatial assessments against CAAS aviation safeguarding layers, and returns structured results back to SkySAFE.

Covers user stories **US-11 through US-20** of the SkySAFE 2.0 backlog.

### Core responsibilities

1. **IFC ingestion & validation** — Accept a CORENET X IFC+SG BIM file by filename (file already landed via SFTP). Validate it can be opened and is structurally usable.
2. **Exterior shell extraction** — Extract *only* the simplified outer envelope of the building. Interior elements are discarded. Retain:
   - 3D geometry of the outer shell
   - Elevation (height above local datum)
   - Façade material attributes (used downstream for radar reflectivity assessment)
   - Gross Floor Area (GFA)
3. **GIS-compatible 3D conversion** — Convert the extracted shell to a 3D model in Singapore's projected CRS (**SVY21 / EPSG:3414**) so it can be intersected with pre-configured aviation safeguarding layers.
4. **Geospatial assessment** — Run the following intersection / impact checks:
   - **Composite Height Template** intersection (which surfaces are penetrated, by how much)
   - **OLS (Obstacle Limitation Surfaces)** intersection — which OLS surface(s) penetrated and penetration depth
   - **ILS (Instrument Landing System) technical templates** — height-template-based ILS impact
   - **Radar** — line-of-sight analysis combined with façade material attributes for interference assessment
   - **GFA** check against pre-configured GFA limit for the site
5. **Structured response** — Return all results as structured text (JSON) so SkySAFE can render the findings to CAAS officers without them needing to log into iEP.
6. **Graceful failure handling** — On any failure, return a structured error payload identifying the stage of failure and the specific error so SkySAFE can surface it to the relevant CAAS officer or to the Public User.

### Out of scope for this Python project

- SkySAFE internet-facing application (Public User submission, application tracking, LOC issuance)
- CAAS division review workflow, ADP processing/approving workflow, notifications
- 3D visualisation in the browser (US-21 to US-25) — iEP provides the model; visualisation is rendered by iEP's separate visualisation layer
- CORENET X compliance checking — that happens in CORENET X *before* the file ever reaches us; we trust the file is compliant
- SFTP transfer itself — the file is already on disk when we are invoked

---

## Tech stack

- **Python**: 3.12 (managed by `uv`)
- **Package / env manager**: `uv` (single source of truth — no `pip`, no `poetry`, no `requirements.txt` editing by hand)
- **API framework**: `fastapi` + `uvicorn` (the iEP processing & validation triggers are HTTP APIs called by SkySAFE)
- **IFC parsing**: `ifcopenshell` (the core dependency — reads IFC4 / IFC+SG)
- **3D geometry**: `trimesh` (mesh ops, boolean intersection, watertightness checks)
- **2D / GIS geometry**: `shapely` (footprint extraction, GFA polygon area)
- **Geospatial dataframes & I/O**: `geopandas` + `fiona` / `pyogrio` (reading OLS / ILS / Composite Height Template layers — likely shapefile, GeoPackage, or multipatch)
- **Coordinate transforms**: `pyproj` (WGS84 ↔ SVY21 / EPSG:3414)
- **Numerics**: `numpy`
- **Raster / DEM (if needed for ground elevation)**: `rasterio`
- **Models / validation**: `pydantic` v2 (all API request / response bodies, all internal DTOs)
- **Logging**: `loguru` (structured logs; one log line per assessment stage)
- **Testing**: `pytest`, `pytest-cov`
- **Lint / format**: `ruff` (lint + format, replaces black + flake8 + isort)
- **Type checking**: `mypy --strict` on the `src/` tree

---

## Project structure

```
.
├── CLAUDE.md
├── README.md
├── pyproject.toml              # uv-managed; deps + tool config here
├── uv.lock
├── .python-version             # 3.12
├── src/
│   └── iep/
│       ├── __init__.py
│       ├── api/                # FastAPI routers — validation & processing endpoints
│       │   ├── validation.py   # US-10
│       │   └── processing.py   # US-11, US-20
│       ├── ifc/                # IFC ingestion + exterior shell extraction
│       │   ├── loader.py
│       │   ├── shell.py        # US-14: outer envelope only
│       │   ├── facade.py       # façade material attribute extraction
│       │   └── gfa.py          # GFA computation
│       ├── geo/                # GIS conversion + CRS handling
│       │   ├── convert.py      # US-15: shell -> SVY21 3D model
│       │   └── crs.py          # SVY21 / EPSG:3414 helpers
│       ├── assess/             # Each assessment is its own module
│       │   ├── height.py       # Composite Height Template intersection
│       │   ├── ols.py          # US-16: OLS intersection
│       │   ├── ils.py          # US-17: ILS technical template
│       │   ├── radar.py        # US-18: line-of-sight + façade material
│       │   └── gfa_limit.py    # US-19: GFA vs pre-defined limit
│       ├── models/             # pydantic schemas for all I/O
│       │   ├── request.py
│       │   ├── response.py     # US-12, US-20 structured response shape
│       │   └── errors.py       # US-13 structured error shape
│       ├── config.py           # paths to GIS layers, GFA limits, OLS layer config
│       └── logging_setup.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│       └── ifc/                # sample IFC+SG files for tests (when CAAS provides them)
├── data/                       # pre-configured CAAS GIS layers (gitignored; mounted at deploy)
│   ├── ols/
│   ├── ils/
│   ├── composite_height/
│   └── radar/
└── scripts/                    # one-off CLIs, e.g. `iep-extract-shell file.ifc`
```

---

## Development setup

```bash
# install uv (once, per machine)
curl -LsSf https://astral.sh/uv/install.sh | sh

# clone + sync
uv sync                         # creates .venv, installs all deps from uv.lock
uv run pytest                   # run tests
uv run ruff check src tests
uv run ruff format src tests
uv run mypy src
uv run uvicorn iep.api.main:app --reload   # local dev server
```

Add a dependency: `uv add ifcopenshell` (never edit `pyproject.toml` deps by hand).
Add a dev-only dep: `uv add --dev pytest-cov`.

---

## Domain glossary (read this before touching the code)

| Term | Meaning |
|---|---|
| **CAAS** | Civil Aviation Authority of Singapore — the agency this system serves |
| **SkySAFE** | The internet-facing CAAS application; the system Public Users submit to and CAAS officers review through |
| **iEP** | The internal processing backend (this project) — does the BIM-GIS extraction and aviation safety assessment |
| **CORENET X** | Singapore's centralised building submission platform. Files reaching us have already passed CORENET X compliance. |
| **IFC+SG** | Singapore profile of the IFC (Industry Foundation Classes) BIM standard. The only BIM format we accept. |
| **BIM** | Building Information Model — the 3D building description we ingest |
| **Exterior shell** | The simplified outer envelope of the building. No interior walls, no furniture, no MEP. |
| **GFA** | Gross Floor Area — total floor area of the building; checked against a pre-defined limit |
| **OLS** | Obstacle Limitation Surfaces — 3D protected surfaces around an airport (Approach, Take-off Climb, Transitional, Inner Horizontal, Conical, etc.). Penetration triggers further review. |
| **ILS** | Instrument Landing System — radio-navigation system. Tall structures near the localiser/glideslope can interfere. Modelled as technical height templates. |
| **Composite Height Template** | Combined height-restriction surface(s) pre-configured by CAAS, used as the first-pass height check |
| **LOC** | Letter of Consent — the final CAAS-issued approval. Not produced by this project. |
| **ADP** | Aerodromes & Air Navigation Services Division Processing / Approving Officer roles in SkySAFE |
| **LOD2** | OGC CityGML Level of Detail 2 — used for surrounding context buildings (not this project) |
| **SVY21** | Singapore's projected CRS, EPSG:3414. All geospatial assessment runs in this CRS. |

---

## Coding conventions

- **All public functions are fully typed.** `mypy --strict` is the gate.
- **All API request/response bodies are pydantic v2 models.** No raw dicts crossing the API boundary.
- **One assessment per module** under `src/iep/assess/`. Each exposes a single `run(model, config) -> AssessmentResult` function. Adding a new assessment must not require touching the others.
- **Errors are structured, not raised across the API boundary.** Internally raise typed exceptions (`IFCLoadError`, `ShellExtractionError`, `AssessmentError`, ...); at the API edge convert to the structured error response shape defined in `models/errors.py` (US-13). The response identifies the **stage** (`ingestion` / `shell_extraction` / `geo_conversion` / `assessment.ols` / ...) and the **specific error detail**.
- **No bare `except`.** Catch the narrowest exception that makes sense.
- **Logging is structured (loguru), one event per stage**, with the IFC filename and the application reference number as bound context.
- **Coordinate systems are explicit in variable names** when ambiguous: `footprint_svy21`, `height_m_amsl` (above mean sea level), `height_m_local`. Never pass bare floats labelled only "height" across module boundaries.
- **Units in code are SI** (metres, square metres). Convert at the edges only.
- **No interior IFC elements ever enter the geometry pipeline.** Filtering happens in `ifc/shell.py` and is the single chokepoint. If a downstream module sees an interior element, that's a bug in `shell.py`.

---

## Response shape (US-12, US-20)

The processing API returns a single structured JSON object with these top-level keys (see `models/response.py`):

```
{
  "application_ref": "...",
  "ifc_filename": "...",
  "shell_extraction": { "status": "ok", "summary": {...} },
  "height_analysis":  { "max_height_m_amsl": ..., "footprint_area_m2": ... },
  "assessments": {
    "composite_height": { "intersects": bool, "penetrations": [...] },
    "ols":              { "intersects": bool, "surfaces_penetrated": [...] },
    "ils":              { "impacts": bool, "templates_breached": [...] },
    "radar":            { "impacts": bool, "los_blockages": [...], "facade_reflectivity": ... },
    "gfa":              { "gfa_m2": ..., "limit_m2": ..., "within_limit": bool }
  },
  "errors": []   // empty on success; structured per-stage errors on failure (US-13)
}
```

`errors` is always present and always a list. On partial failure (e.g., shell extraction OK but OLS assessment failed), successful stages still report and the failing stage appears in `errors` with its `stage` and `detail`.

---

## Testing approach

- **Unit tests** mock IFC inputs at the `ifcopenshell` object level — do not require an actual file on disk for the bulk of logic.
- **Integration tests** use real sample IFC+SG files in `tests/fixtures/ifc/`. CAAS to provide samples (raised in US-14 clarification); until then, use anonymised generic IFC + manually verified expected outputs.
- **Assessment modules** each ship with a test that pins the result against a hand-computed expected value for one fixture.
- **API tests** use FastAPI's `TestClient`, hitting the validation and processing endpoints.
- Coverage target: **≥85% on `src/iep/assess/` and `src/iep/ifc/`** (these are the modules where a regression silently corrupts a CAAS decision).
- Run before every commit:
  ```bash
  uv run ruff check src tests && uv run mypy src && uv run pytest
  ```

---

## Open clarifications (track here until resolved with CAAS / NCS)

These are flagged in the user stories and gate parts of the implementation:

- **Sample IFC+SG file from CAAS** (US-14 clarification) — needed to pin shell extraction logic to real-world structure.
- **Formats of Composite Height Template and ILS technical template layers** (US-22 clarification) — shapefile / file geodatabase / multipatch? Affects `geo/` loader choices.
- **Whether all OLS 3D surfaces are pre-configured and accessible to iEP** (US-20 clarification).
- **Whether ILS and Radar GIS layers are CAAS-held or require API/SFTP from another agency** (US-20 clarification).
- **Radar facade reflectivity model** — what material → reflectivity mapping does CAAS use? Need the lookup table.

Until each is resolved, the corresponding module exposes its inputs via `config.py` with placeholder values and a `# TODO(caas-clarification: US-XX)` marker.

---

## Things Claude should *not* do in this codebase

- Don't add a new top-level dependency without `uv add`; never hand-edit `pyproject.toml` deps or `uv.lock`.
- Don't introduce `requirements.txt`, `setup.py`, `poetry.lock`, or `pipenv` artefacts.
- Don't let interior IFC elements leak past `src/iep/ifc/shell.py`.
- Don't raise exceptions across the FastAPI boundary — convert to the structured error response (US-13).
- Don't change the response schema in `models/response.py` without flagging it: SkySAFE parses this and a breaking change ripples into their UI.
- Don't hardcode coordinates or assume WGS84; everything geospatial is in **SVY21 (EPSG:3414)** unless explicitly noted at the edge.
- Don't add a CORENET X compliance check — that's CORENET X's job, not ours.
