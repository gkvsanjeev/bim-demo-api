# iEP SkySAFE 2.0 — API Reference

**Service:** iEP BIM Shell Extraction & Aviation Safety Assessment  
**Version:** 0.1.0  
**Base URL (local dev):** `http://localhost:8000`

> **Interactive docs** — start the server and open:
> - Swagger UI: `http://localhost:8000/docs`
> - ReDoc: `http://localhost:8000/redoc`
> - OpenAPI JSON: `http://localhost:8000/openapi.json`

---

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Liveness check |
| POST | `/processing/extract-shell` | Extract exterior shell + generate PDF in background |
| GET | `/processing/analysis-report/{application_ref}` | Download generated PDF |
| POST | `/processing/analyse` | Run selected assessments + return JSON and PDF URL in one call |

---

## GET `/health`

Liveness check. Returns immediately.

**Response `200`**

```json
{ "status": "ok" }
```

---

## POST `/processing/extract-shell`

Loads an IFC file, extracts the exterior shell, computes height and GFA, and surveys façade materials. Returns structured JSON. Generates a PDF report **in the background** — retrieve it afterwards via `GET /processing/analysis-report/{application_ref}`.

All five assessment stages (CHT, OLS, ILS, GFA limit, Radar) are run with their current configuration (demo data until CAAS GIS layers are delivered).

### Request body

```json
{
  "application_ref": "APP-002",
  "ifc_filename": "ZHA-B-BWK-C-MR-R18.ifc"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `application_ref` | string | yes | SkySAFE application reference number |
| `ifc_filename` | string | yes | Filename of the IFC file already on the SFTP landing directory |

### Response `200` — `ProcessingResponse`

```json
{
  "application_ref": "APP-002",
  "ifc_filename": "ZHA-B-BWK-C-MR-R18.ifc",
  "shell_extraction": {
    "status": "ok",
    "element_count": 1567,
    "vertex_count": 51562,
    "triangle_count": 97124
  },
  "height_analysis": {
    "elevation_m_local": 0.0,
    "min_z_m": -2.05,
    "max_z_m": 69.86,
    "height_m": 71.91
  },
  "gfa": {
    "gfa_m2": 74749.9
  },
  "facade_materials": {
    "unique_material_count": 5,
    "materials": [
      { "name": "NLRS_f2_beton prefab", "element_count": 915 },
      { "name": "NLRS_f2_beton ihwg",   "element_count": 588 }
    ]
  },
  "errors": []
}
```

| Field | Type | Description |
|-------|------|-------------|
| `application_ref` | string | Echoed from request |
| `ifc_filename` | string | Echoed from request |
| `shell_extraction.status` | `"ok"` \| `"error"` | Extraction status |
| `shell_extraction.element_count` | integer | Number of exterior IFC elements extracted |
| `shell_extraction.vertex_count` | integer | Mesh vertices |
| `shell_extraction.triangle_count` | integer | Mesh triangles |
| `height_analysis.elevation_m_local` | float | `IfcSite.RefElevation` (metres, local datum) |
| `height_analysis.min_z_m` | float | Lowest point of shell (metres, local) |
| `height_analysis.max_z_m` | float | Highest point of shell (metres, local) |
| `height_analysis.height_m` | float | `max_z_m − min_z_m` |
| `gfa.gfa_m2` | float | Gross floor area (m²) |
| `facade_materials.unique_material_count` | integer | Number of distinct material types |
| `facade_materials.materials` | array | `name` + `element_count` per material |
| `errors` | array | Empty on success; `StageError` objects on failure |

**Note:** After receiving the JSON, the PDF is being generated in the background. Poll `GET /processing/analysis-report/{application_ref}` — a `202` means it is still generating; a `200` returns the file.

---

## GET `/processing/analysis-report/{application_ref}`

Download the PDF report for a previously processed application.

### Path parameter

| Parameter | Type | Description |
|-----------|------|-------------|
| `application_ref` | string | SkySAFE application reference (e.g. `APP-002`) |

### Responses

| Status | Content-Type | Description |
|--------|--------------|-------------|
| `200` | `application/pdf` | PDF report ready — file download |
| `202` | `application/json` | PDF still generating — retry in a few seconds |
| `404` | `application/json` | No result found; call `POST /processing/extract-shell` first |

**`202` body**

```json
{
  "detail": "PDF is still being generated -- please retry in a few seconds.",
  "application_ref": "APP-002"
}
```

**`404` body**

```json
{
  "detail": "No processing result found for this application_ref. Call POST /processing/extract-shell first.",
  "application_ref": "APP-002"
}
```

---

## POST `/processing/analyse`

**Recommended endpoint for frontend integration.**

Runs the IFC pipeline and the caller-selected subset of aviation safety assessments in a single call. The PDF is generated **synchronously** — `pdf_url` in the response is immediately valid.

### Request body

```json
{
  "application_ref": "APP-003",
  "ifc_filename": "building.ifc",
  "assessments": {
    "composite_height_template": true,
    "ols_intersection": true,
    "ils_technical_template": false,
    "gfa": false,
    "radar": true
  }
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `application_ref` | string | yes | — | SkySAFE application reference number |
| `ifc_filename` | string | yes | — | Filename of the IFC file on the SFTP landing directory |
| `assessments` | object | no | all `true` | Which assessment checks to include (see below) |

#### `assessments` object

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `composite_height_template` | boolean | `true` | CHT intersection check (Stage 5) |
| `ols_intersection` | boolean | `true` | OLS surface intersection check (Stage 6) |
| `ils_technical_template` | boolean | `true` | ILS technical template impact check (Stage 7) |
| `gfa` | boolean | `true` | Gross Floor Area limit check |
| `radar` | boolean | `true` | Radar line-of-sight + façade reflectivity check |

Assessments set to `false` appear as **PENDING** in the generated PDF rather than being omitted.

### Response `200` — `AnalysisResponse`

All fields from `ProcessingResponse` (see above) plus:

```json
{
  "application_ref": "APP-003",
  "ifc_filename": "building.ifc",
  "shell_extraction": { ... },
  "height_analysis": { ... },
  "gfa": { ... },
  "facade_materials": { ... },
  "errors": [],
  "assessments_run": {
    "composite_height_template": true,
    "ols_intersection": true,
    "ils_technical_template": false,
    "gfa": false,
    "radar": true
  },
  "pdf_url": "/processing/analysis-report/APP-003"
}
```

| Additional field | Type | Description |
|-----------------|------|-------------|
| `assessments_run` | object | Echoes the `assessments` flags that were applied |
| `pdf_url` | string | Path to download the PDF — immediately valid |

To download the PDF, issue a `GET` to the value of `pdf_url` (prepend the base URL in production).

---

## Data models

### `StageError`

Appears in the `errors` array when a pipeline stage fails.

```json
{ "stage": "ingestion", "detail": "File not found: building.ifc" }
```

| Field | Type | Description |
|-------|------|-------------|
| `stage` | string | `ingestion` \| `shell_extraction` \| `geo_conversion` \| `assessment.cht` \| `assessment.ols` \| `assessment.ils` \| `assessment.radar` \| `assessment.gfa` |
| `detail` | string | Human-readable error description |

---

## Error handling

The API never raises unhandled exceptions across the boundary. On failure, the endpoint still returns `200` with `errors` populated and a PDF that documents the failure stage. The frontend should check `errors.length > 0` to detect partial or full failure.

**Example — IFC file not found:**

```json
{
  "application_ref": "APP-003",
  "ifc_filename": "missing.ifc",
  "shell_extraction": { "status": "error", "element_count": 0, "vertex_count": 0, "triangle_count": 0 },
  "height_analysis": { "elevation_m_local": 0.0, "min_z_m": 0.0, "max_z_m": 0.0, "height_m": 0.0 },
  "gfa": { "gfa_m2": 0.0 },
  "facade_materials": { "unique_material_count": 0, "materials": [] },
  "errors": [
    { "stage": "ingestion", "detail": "IFC file not found: missing.ifc" }
  ],
  "assessments_run": { ... },
  "pdf_url": "/processing/analysis-report/APP-003"
}
```

---

## Frontend integration guide

### Recommended flow

```
1. User selects assessments via checkboxes → build assessments object
2. POST /processing/analyse  →  receive JSON + pdf_url
3. Render JSON results in the UI
4. Offer "Download Report" button that opens GET {pdf_url}
```

### Minimal fetch example (JavaScript)

```js
const response = await fetch('/processing/analyse', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    application_ref: 'APP-003',
    ifc_filename: 'building.ifc',
    assessments: {
      composite_height_template: true,
      ols_intersection: true,
      ils_technical_template: false,
      gfa: true,
      radar: false,
    },
  }),
});

const data = await response.json();

// data.errors — check for pipeline failures
// data.height_analysis.height_m — building height
// data.pdf_url — pass to window.open() or an <a href>
window.open(data.pdf_url);
```

### Assessment checkbox → field name mapping

| UI label | Request field |
|----------|--------------|
| Composite Height Template | `composite_height_template` |
| OLS Intersection | `ols_intersection` |
| ILS Technical Template | `ils_technical_template` |
| Gross Floor Area (GFA) | `gfa` |
| Radar | `radar` |
