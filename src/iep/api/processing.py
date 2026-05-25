from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse, Response
from loguru import logger

from iep.config import IFC_DIR, RESULTS_DIR
from iep.ifc.loader import load_ifc
from iep.ifc.shell import extract_exterior_shell
from iep.models.errors import IFCLoadError, ShellExtractionError, StageError
from iep.models.request import AnalysisRequest, ProcessingRequest
from iep.models.response import (
    AnalysisResponse,
    FacadeMaterialSummary,
    GFAResult,
    HeightAnalysis,
    MaterialEntry,
    ProcessingResponse,
    ShellExtractionSummary,
)
from iep.reports.pdf import CHTResult, ILSResult, OLSResult, generate_pdf

router = APIRouter(prefix="/processing", tags=["processing"])

# ── Simulated assessment data ──────────────────────────────────────────────────
# Replace each with the real assessment module result once CAAS GIS layers arrive.
_DEMO_CHT = CHTResult(
    intersects=True,
    max_permitted_height_m_amsl=88.85,
    building_peak_m_amsl=101.55,
    penetration_depth_m=12.70,
    penetrations=[{
        "zone":             "CHT Zone A -- Primary Obstacle Limitation",
        "permitted_m_amsl": 88.85,
        "building_m_amsl":  101.55,
        "excess_m":         12.70,
    }],
)

_DEMO_OLS = OLSResult(
    intersects=True,
    surfaces_penetrated=[{
        "surface":     "Transitional Surface",
        "runway":      "RWY 02L/20R",
        "aerodrome":   "Singapore Changi Airport (WSSS)",
        "surface_height_at_point_m_amsl": 94.13,
        "building_m_amsl":     101.55,
        "penetration_depth_m": 7.42,
        "lateral_offset_m":    284.0,
    }],
    surfaces_clear=[
        "Approach Surface",
        "Take-off Climb Surface",
        "Inner Horizontal Surface",
        "Conical Surface",
        "Outer Horizontal Surface",
    ],
)

_DEMO_ILS = ILSResult(
    impacts=True,
    templates_breached=[{
        "template_id":    "ILS-WSSS-02L-LOC",
        "system":         "Localiser (LOC)",
        "runway":         "RWY 02L",
        "aerodrome":      "Singapore Changi Airport (WSSS)",
        "permitted_m_amsl": 85.00,
        "building_m_amsl":  101.55,
        "excess_m":         16.55,
        "azimuth_from_antenna_deg": 312.4,
        "distance_from_antenna_m":  1840.0,
    }],
    templates_clear=["ILS-WSSS-02L-GP", "ILS-WSSS-20R-LOC", "ILS-WSSS-20R-GP"],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _pdf_path(application_ref: str) -> Path:
    return RESULTS_DIR / f"{application_ref}.pdf"


def _load_cached_result(application_ref: str) -> ProcessingResponse | None:
    result_path = RESULTS_DIR / f"{application_ref}.json"
    if result_path.exists():
        return ProcessingResponse.model_validate_json(result_path.read_text(encoding="utf-8"))
    return None


def _save_result(result: ProcessingResponse) -> None:
    result_path = RESULTS_DIR / f"{result.application_ref}.json"
    result_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")


def _generate_and_save_pdf(response: ProcessingResponse) -> None:
    """Background task: build PDF from the processing result and save to results/."""
    log = logger.bind(application_ref=response.application_ref)
    try:
        log.info("Background PDF generation started")
        pdf_bytes = generate_pdf(
            response,
            cht=_DEMO_CHT,
            ols=_DEMO_OLS,
            ils=_DEMO_ILS,
            generated_at=datetime.now(timezone.utc),
        )
        _pdf_path(response.application_ref).write_bytes(pdf_bytes)
        log.info("PDF saved -- {} bytes -> {}.pdf", len(pdf_bytes), response.application_ref)
    except Exception as exc:
        log.error("Background PDF generation failed: {}", exc)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/extract-shell", response_model=ProcessingResponse)
async def extract_shell(req: ProcessingRequest, bg: BackgroundTasks) -> ProcessingResponse:
    """
    Extract the exterior shell of a building from an IFC file and return structured JSON.

    The IFC file must already be present on disk (landed via SFTP).
    A cached JSON result is returned immediately if one exists for this application_ref.

    After the JSON response is sent, a PDF report is generated in the background and
    saved to results/{application_ref}.pdf.  Retrieve it via:
        GET /processing/analysis-report/{application_ref}
    """
    log = logger.bind(application_ref=req.application_ref, ifc_filename=req.ifc_filename)

    cached = _load_cached_result(req.application_ref)
    if cached is not None:
        log.info("Returning cached result")
        bg.add_task(_generate_and_save_pdf, cached)
        return cached

    ifc_path = IFC_DIR / req.ifc_filename
    log.info("Starting shell extraction")

    try:
        model = load_ifc(ifc_path)
    except IFCLoadError as exc:
        log.error("IFC load failed: {}", exc)
        response = ProcessingResponse(
            application_ref=req.application_ref,
            ifc_filename=req.ifc_filename,
            shell_extraction=ShellExtractionSummary(
                status="error", element_count=0, vertex_count=0, triangle_count=0
            ),
            height_analysis=HeightAnalysis(
                elevation_m_local=0.0, min_z_m=0.0, max_z_m=0.0, height_m=0.0
            ),
            gfa=GFAResult(gfa_m2=0.0),
            facade_materials=FacadeMaterialSummary(unique_material_count=0, materials=[]),
            errors=[StageError(stage="ingestion", detail=str(exc))],
        )
        _save_result(response)
        bg.add_task(_generate_and_save_pdf, response)
        return response

    try:
        result = extract_exterior_shell(model)
    except ShellExtractionError as exc:
        log.error("Shell extraction failed: {}", exc)
        response = ProcessingResponse(
            application_ref=req.application_ref,
            ifc_filename=req.ifc_filename,
            shell_extraction=ShellExtractionSummary(
                status="error", element_count=0, vertex_count=0, triangle_count=0
            ),
            height_analysis=HeightAnalysis(
                elevation_m_local=0.0, min_z_m=0.0, max_z_m=0.0, height_m=0.0
            ),
            gfa=GFAResult(gfa_m2=0.0),
            facade_materials=FacadeMaterialSummary(unique_material_count=0, materials=[]),
            errors=[StageError(stage="shell_extraction", detail=str(exc))],
        )
        _save_result(response)
        bg.add_task(_generate_and_save_pdf, response)
        return response

    material_counts = Counter(
        m.material_name for m in result.facade_materials if m.material_name
    )
    log.info("Shell extraction complete -- height {:.2f} m, GFA {:.1f} m2",
             result.height_m, result.gfa_m2)

    response = ProcessingResponse(
        application_ref=req.application_ref,
        ifc_filename=req.ifc_filename,
        shell_extraction=ShellExtractionSummary(
            status="ok",
            element_count=result.element_count,
            vertex_count=int(result.vertices_m.shape[0]),
            triangle_count=int(result.faces.shape[0]),
        ),
        height_analysis=HeightAnalysis(
            elevation_m_local=result.elevation_m_local,
            min_z_m=round(result.min_z_m, 3),
            max_z_m=round(result.max_z_m, 3),
            height_m=round(result.height_m, 3),
        ),
        gfa=GFAResult(gfa_m2=round(result.gfa_m2, 2)),
        facade_materials=FacadeMaterialSummary(
            unique_material_count=len(material_counts),
            materials=[
                MaterialEntry(name=name, element_count=count)
                for name, count in material_counts.most_common()
            ],
        ),
        errors=[],
    )
    _save_result(response)
    bg.add_task(_generate_and_save_pdf, response)
    return response


@router.get(
    "/analysis-report/{application_ref}",
    response_class=FileResponse,
    responses={
        200: {"content": {"application/pdf": {}}, "description": "PDF analysis report"},
        202: {"description": "PDF is still being generated -- retry shortly"},
        404: {"description": "No result found for this application_ref"},
    },
)
async def get_analysis_report(application_ref: str) -> Response:
    """
    Download the PDF report for a previously processed application.

    The PDF is generated in the background after POST /processing/extract-shell.
    If the PDF is not yet ready, returns HTTP 202 (retry in a few seconds).
    If no processing result exists at all, returns HTTP 404.
    """
    pdf = _pdf_path(application_ref)
    json_result = RESULTS_DIR / f"{application_ref}.json"

    if pdf.exists():
        filename = f"iep_report_{application_ref}.pdf"
        return FileResponse(
            path=str(pdf),
            media_type="application/pdf",
            filename=filename,
        )

    if json_result.exists():
        return JSONResponse(
            status_code=202,
            content={
                "detail": "PDF is still being generated -- please retry in a few seconds.",
                "application_ref": application_ref,
            },
        )

    return JSONResponse(
        status_code=404,
        content={
            "detail": "No processing result found for this application_ref. "
                      "Call POST /processing/extract-shell first.",
            "application_ref": application_ref,
        },
    )


# ── Error response builder ─────────────────────────────────────────────────────

def _error_response(application_ref: str, ifc_filename: str, stage: str, exc: Exception) -> ProcessingResponse:
    return ProcessingResponse(
        application_ref=application_ref,
        ifc_filename=ifc_filename,
        shell_extraction=ShellExtractionSummary(
            status="error", element_count=0, vertex_count=0, triangle_count=0
        ),
        height_analysis=HeightAnalysis(
            elevation_m_local=0.0, min_z_m=0.0, max_z_m=0.0, height_m=0.0
        ),
        gfa=GFAResult(gfa_m2=0.0),
        facade_materials=FacadeMaterialSummary(unique_material_count=0, materials=[]),
        errors=[StageError(stage=stage, detail=str(exc))],
    )


@router.post("/analyse", response_model=AnalysisResponse)
async def analyse(req: AnalysisRequest) -> AnalysisResponse:
    """
    Run selected aviation safety assessments on an IFC file.

    The caller specifies which of the five assessment checks to include via the
    ``assessments`` body object.  Unchecked assessments appear as PENDING in the
    generated PDF rather than being omitted entirely.

    Returns the full structured JSON result **and** a ``pdf_url`` pointing to the
    ready-to-download PDF — no polling needed.
    """
    log = logger.bind(application_ref=req.application_ref, ifc_filename=req.ifc_filename)
    log.info("Starting selective analysis -- assessments={}", req.assessments.model_dump())

    ifc_path = IFC_DIR / req.ifc_filename
    generated_at = datetime.now(timezone.utc)
    pdf_url = f"/processing/analysis-report/{req.application_ref}"

    # ── IFC load ───────────────────────────────────────────────────────────────
    try:
        model = load_ifc(ifc_path)
    except IFCLoadError as exc:
        log.error("IFC load failed: {}", exc)
        base = _error_response(req.application_ref, req.ifc_filename, "ingestion", exc)
        _save_result(base)
        _pdf_path(req.application_ref).write_bytes(generate_pdf(base, generated_at=generated_at))
        return AnalysisResponse(**base.model_dump(), assessments_run=req.assessments, pdf_url=pdf_url)

    # ── Shell extraction ────────────────────────────────────────────────────────
    try:
        result = extract_exterior_shell(model)
    except ShellExtractionError as exc:
        log.error("Shell extraction failed: {}", exc)
        base = _error_response(req.application_ref, req.ifc_filename, "shell_extraction", exc)
        _save_result(base)
        _pdf_path(req.application_ref).write_bytes(generate_pdf(base, generated_at=generated_at))
        return AnalysisResponse(**base.model_dump(), assessments_run=req.assessments, pdf_url=pdf_url)

    material_counts = Counter(m.material_name for m in result.facade_materials if m.material_name)
    log.info("Shell extraction complete -- height {:.2f} m, GFA {:.1f} m²", result.height_m, result.gfa_m2)

    base = ProcessingResponse(
        application_ref=req.application_ref,
        ifc_filename=req.ifc_filename,
        shell_extraction=ShellExtractionSummary(
            status="ok",
            element_count=result.element_count,
            vertex_count=int(result.vertices_m.shape[0]),
            triangle_count=int(result.faces.shape[0]),
        ),
        height_analysis=HeightAnalysis(
            elevation_m_local=result.elevation_m_local,
            min_z_m=round(result.min_z_m, 3),
            max_z_m=round(result.max_z_m, 3),
            height_m=round(result.height_m, 3),
        ),
        gfa=GFAResult(gfa_m2=round(result.gfa_m2, 2)),
        facade_materials=FacadeMaterialSummary(
            unique_material_count=len(material_counts),
            materials=[
                MaterialEntry(name=name, element_count=count)
                for name, count in material_counts.most_common()
            ],
        ),
        errors=[],
    )

    # ── Selected assessments (demo data; replace when CAAS GIS layers arrive) ──
    sel = req.assessments
    cht = _DEMO_CHT if sel.composite_height_template else None
    ols = _DEMO_OLS if sel.ols_intersection else None
    ils = _DEMO_ILS if sel.ils_technical_template else None
    # radar: no implementation yet — always PENDING regardless of the flag

    # ── Generate PDF synchronously so the URL is immediately valid ─────────────
    pdf_bytes = generate_pdf(base, cht=cht, ols=ols, ils=ils, generated_at=generated_at)
    _pdf_path(req.application_ref).write_bytes(pdf_bytes)
    _save_result(base)
    log.info("PDF saved -- {} bytes -> {}.pdf", len(pdf_bytes), req.application_ref)

    return AnalysisResponse(**base.model_dump(), assessments_run=sel, pdf_url=pdf_url)
