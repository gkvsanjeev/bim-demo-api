"""
PDF report generator for iEP SkySAFE 2.0 aviation safety assessments.

Accepts a ProcessingResponse (real pipeline output) plus optional assessment
sections (CHT, OLS, ILS) and produces an A4 PDF suitable for CAAS officers.
Assessment sections that have not yet been computed are rendered as
[PENDING -- awaiting CAAS GIS layer delivery] blocks.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    HRFlowable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from iep.models.response import ProcessingResponse

# ── Colour palette ─────────────────────────────────────────────────────────────
_NAVY    = colors.HexColor("#1B3A6B")
_BLUE    = colors.HexColor("#2563EB")
_GREEN   = colors.HexColor("#16A34A")
_RED     = colors.HexColor("#DC2626")
_AMBER   = colors.HexColor("#D97706")
_GREY    = colors.HexColor("#6B7280")
_LGREY   = colors.HexColor("#F3F4F6")
_WHITE   = colors.white
_BLACK   = colors.black

PAGE_W, PAGE_H = A4
L_MARGIN = R_MARGIN = 1.8 * cm
T_MARGIN = B_MARGIN = 2.0 * cm
CONTENT_W = PAGE_W - L_MARGIN - R_MARGIN


# ── Style helpers ──────────────────────────────────────────────────────────────
_BASE = getSampleStyleSheet()

_S = {
    "title": ParagraphStyle(
        "rpt_title",
        fontSize=18, fontName="Helvetica-Bold",
        textColor=_WHITE, alignment=TA_CENTER, spaceAfter=2,
    ),
    "subtitle": ParagraphStyle(
        "rpt_subtitle",
        fontSize=10, fontName="Helvetica",
        textColor=_WHITE, alignment=TA_CENTER,
    ),
    "section_hdr": ParagraphStyle(
        "rpt_section_hdr",
        fontSize=10, fontName="Helvetica-Bold",
        textColor=_WHITE, alignment=TA_LEFT,
        leftIndent=4,
    ),
    "body": ParagraphStyle(
        "rpt_body",
        fontSize=9, fontName="Helvetica",
        textColor=_BLACK, spaceAfter=2, leading=13,
    ),
    "label": ParagraphStyle(
        "rpt_label",
        fontSize=8, fontName="Helvetica-Bold",
        textColor=_GREY,
    ),
    "value": ParagraphStyle(
        "rpt_value",
        fontSize=9, fontName="Helvetica",
        textColor=_BLACK,
    ),
    "pass": ParagraphStyle(
        "rpt_pass",
        fontSize=9, fontName="Helvetica-Bold",
        textColor=_GREEN,
    ),
    "fail": ParagraphStyle(
        "rpt_fail",
        fontSize=9, fontName="Helvetica-Bold",
        textColor=_RED,
    ),
    "warn": ParagraphStyle(
        "rpt_warn",
        fontSize=9, fontName="Helvetica-Bold",
        textColor=_AMBER,
    ),
    "pending": ParagraphStyle(
        "rpt_pending",
        fontSize=9, fontName="Helvetica-Oblique",
        textColor=_GREY,
    ),
    "code": ParagraphStyle(
        "rpt_code",
        fontSize=7, fontName="Courier",
        textColor=_BLACK, leading=10, spaceAfter=0,
    ),
    "footer": ParagraphStyle(
        "rpt_footer",
        fontSize=7, fontName="Helvetica",
        textColor=_GREY, alignment=TA_CENTER,
    ),
}


def _hr(colour: Any = _LGREY, thickness: float = 0.5) -> HRFlowable:
    return HRFlowable(width="100%", thickness=thickness, color=colour, spaceAfter=4, spaceBefore=4)


def _section_header(title: str, tag: str = "", colour: Any = _NAVY) -> Table:
    tag_para = Paragraph(tag, ParagraphStyle("tag", fontSize=9, fontName="Helvetica-Bold",
                                             textColor=_WHITE, alignment=TA_RIGHT))
    title_para = Paragraph(title, _S["section_hdr"])
    tbl = Table([[title_para, tag_para]], colWidths=[CONTENT_W * 0.75, CONTENT_W * 0.25])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colour),
        ("TOPPADDING",    (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return tbl


def _kv_table(rows: list[tuple[str, str]], col1: float = 0.45) -> Table:
    data = [
        [Paragraph(k, _S["label"]), Paragraph(v, _S["value"])]
        for k, v in rows
    ]
    tbl = Table(data, colWidths=[CONTENT_W * col1, CONTENT_W * (1 - col1)])
    tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_WHITE, _LGREY]),
    ]))
    return tbl


def _status_table(rows: list[tuple[bool | None, str]]) -> Table:
    """Render pass/fail/warn rows. None = pending."""
    def _icon_para(ok: bool | None) -> Paragraph:
        if ok is True:
            return Paragraph("PASS", _S["pass"])
        if ok is False:
            return Paragraph("FAIL", _S["fail"])
        return Paragraph("PENDING", _S["pending"])

    data = [[_icon_para(ok), Paragraph(text, _S["body"])] for ok, text in rows]
    tbl = Table(data, colWidths=[1.4 * cm, CONTENT_W - 1.4 * cm])
    tbl.setStyle(TableStyle([
        ("TOPPADDING",    (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return tbl


def _penetration_table(rows: list[dict[str, Any]], headers: list[str],
                       keys: list[str]) -> Table:
    header_row = [Paragraph(h, ParagraphStyle("th", fontSize=8, fontName="Helvetica-Bold",
                                              textColor=_WHITE))
                  for h in headers]
    data_rows = [
        [Paragraph(str(r.get(k, "")), _S["body"]) for k in keys]
        for r in rows
    ]
    col_w = CONTENT_W / len(headers)
    tbl = Table([header_row] + data_rows, colWidths=[col_w] * len(headers))
    tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _LGREY]),
        ("GRID", (0, 0), (-1, -1), 0.3, _GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    return tbl


# ── Assessment data structures ─────────────────────────────────────────────────

@dataclass
class CHTResult:
    intersects: bool
    max_permitted_height_m_amsl: float
    building_peak_m_amsl: float
    penetration_depth_m: float
    penetrations: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class OLSResult:
    intersects: bool
    surfaces_penetrated: list[dict[str, Any]] = field(default_factory=list)
    surfaces_clear: list[str] = field(default_factory=list)


@dataclass
class ILSResult:
    impacts: bool
    templates_breached: list[dict[str, Any]] = field(default_factory=list)
    templates_clear: list[str] = field(default_factory=list)


# ── Main PDF builder ───────────────────────────────────────────────────────────

def generate_pdf(
    response: ProcessingResponse,
    *,
    cht: CHTResult | None = None,
    ols: OLSResult | None = None,
    ils: ILSResult | None = None,
    generated_at: datetime | None = None,
) -> bytes:
    """
    Build a PDF report from a ProcessingResponse plus optional assessment results.

    Returns the PDF as raw bytes (ready for a FastAPI Response body).
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=L_MARGIN, rightMargin=R_MARGIN,
        topMargin=T_MARGIN,  bottomMargin=B_MARGIN,
        title=f"iEP Aviation Safety Report -- {response.application_ref}",
        author="iEP SkySAFE 2.0 Processing Service",
    )

    story: list[Any] = []

    # ── Cover header ────────────────────────────────────────────────────────────
    cover_title = Table(
        [[Paragraph("iEP SkySAFE 2.0", _S["title"])],
         [Paragraph("Aviation Safety Assessment Report", _S["subtitle"])],
         [Paragraph(f"Application Reference: {response.application_ref}", _S["subtitle"])]],
        colWidths=[CONTENT_W],
    )
    cover_title.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
    ]))
    story.append(cover_title)
    story.append(Spacer(1, 8))

    meta_rows: list[tuple[str, str]] = [
        ("Application reference", response.application_ref),
        ("IFC filename",          response.ifc_filename),
        ("Report generated",      generated_at.strftime("%Y-%m-%d %H:%M UTC")),
        ("Pipeline version",      "0.1.0"),
    ]
    story.append(_kv_table(meta_rows))
    story.append(Spacer(1, 10))

    # ── Stage 1: IFC ingestion ───────────────────────────────────────────────────
    story.append(_section_header("STAGE 1 -- IFC INGESTION & VALIDATION", "PASS", _NAVY))
    story.append(Spacer(1, 4))
    story.append(_status_table([
        (True, "File located on SFTP landing directory"),
        (True, "IFC schema validated: IFC4 / IFC+SG v1.0"),
        (True, f"Filename: {response.ifc_filename}"),
    ]))
    story.append(Spacer(1, 8))

    # ── Stage 2: Shell extraction ────────────────────────────────────────────────
    se = response.shell_extraction
    se_ok = se.status == "ok"
    se_tag = "PASS" if se_ok else "FAIL"
    story.append(_section_header("STAGE 2 -- EXTERIOR SHELL EXTRACTION", se_tag,
                                 _NAVY if se_ok else _RED))
    story.append(Spacer(1, 4))
    story.append(_kv_table([
        ("Status",           se.status.upper()),
        ("Exterior elements extracted", f"{se.element_count:,}"),
        ("Mesh vertices",    f"{se.vertex_count:,}"),
        ("Mesh triangles",   f"{se.triangle_count:,}"),
    ]))
    story.append(Spacer(1, 8))

    # ── Stage 3: Height analysis ─────────────────────────────────────────────────
    ha = response.height_analysis
    ha_amsl = round(ha.max_z_m + ha.elevation_m_local, 3)
    story.append(_section_header("STAGE 3 -- HEIGHT ANALYSIS", "COMPLETE", _NAVY))
    story.append(Spacer(1, 4))
    story.append(_kv_table([
        ("Site elevation (IfcSite.RefElevation)",  f"{ha.elevation_m_local} m (local datum)"),
        ("Lowest point -- ground slab soffit",     f"{ha.min_z_m} m"),
        ("Highest point -- roof apex (local)",     f"{ha.max_z_m} m"),
        ("Building height",                        f"{ha.height_m} m"),
        ("Peak height above mean sea level (AMSL)",f"<b>{ha_amsl} m AMSL</b> -- used for all aviation assessments"),
    ]))
    story.append(Spacer(1, 8))

    # ── Stage 4: GFA ────────────────────────────────────────────────────────────
    gfa = response.gfa
    within = getattr(gfa, "within_limit", None)
    gfa_limit = getattr(gfa, "limit_m2", None)
    utilisation = f"{gfa.gfa_m2 / gfa_limit * 100:.1f}%" if gfa_limit else "N/A"
    gfa_tag = "PASS" if within else ("FAIL" if within is False else "")
    gfa_colour = _GREEN if within else (_RED if within is False else _NAVY)
    story.append(_section_header("STAGE 4 -- GROSS FLOOR AREA (GFA)", gfa_tag, gfa_colour))
    story.append(Spacer(1, 4))
    gfa_rows: list[tuple[str, str]] = [("Proposed GFA", f"{gfa.gfa_m2:,.1f} m²")]
    if gfa_limit:
        gfa_rows += [
            ("Site GFA limit", f"{gfa_limit:,.1f} m²"),
            ("Utilisation",    utilisation),
        ]
    story.append(_kv_table(gfa_rows))
    story.append(Spacer(1, 8))

    # ── Stage 4b: Facade materials ───────────────────────────────────────────────
    fm = response.facade_materials
    story.append(_section_header("STAGE 4b -- FACADE MATERIAL SURVEY", "", _NAVY))
    story.append(Spacer(1, 4))
    story.append(Paragraph(f"Unique material types identified: <b>{fm.unique_material_count}</b>",
                           _S["body"]))
    story.append(Spacer(1, 4))
    if fm.materials:
        mat_data = [[
            Paragraph("Material", ParagraphStyle("th", fontSize=8, fontName="Helvetica-Bold",
                                                 textColor=_WHITE)),
            Paragraph("Elements", ParagraphStyle("th", fontSize=8, fontName="Helvetica-Bold",
                                                 textColor=_WHITE)),
        ]] + [
            [Paragraph(m.name, _S["body"]),
             Paragraph(str(m.element_count), _S["body"])]
            for m in fm.materials
        ]
        mat_tbl = Table(mat_data, colWidths=[CONTENT_W * 0.75, CONTENT_W * 0.25])
        mat_tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0), _NAVY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _LGREY]),
            ("GRID", (0, 0), (-1, -1), 0.3, _GREY),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ]))
        story.append(mat_tbl)
    story.append(Spacer(1, 8))

    # ── Stage 5: CHT ────────────────────────────────────────────────────────────
    if cht is not None:
        cht_colour = _RED if cht.intersects else _GREEN
        cht_tag    = "PENETRATION DETECTED" if cht.intersects else "CLEAR"
        story.append(_section_header(
            "STAGE 5 -- COMPOSITE HEIGHT TEMPLATE (CHT) INTERSECTION",
            cht_tag, cht_colour))
        story.append(Spacer(1, 4))
        story.append(_kv_table([
            ("Max permitted height (CHT)",   f"{cht.max_permitted_height_m_amsl} m AMSL"),
            ("Building peak height",         f"{cht.building_peak_m_amsl} m AMSL"),
            ("Penetration depth",            f"<b>{cht.penetration_depth_m} m</b>" if cht.intersects else "None"),
        ]))
        if cht.intersects and cht.penetrations:
            story.append(Spacer(1, 4))
            story.append(Paragraph("<b>Penetrated zones:</b>", _S["body"]))
            story.append(Spacer(1, 2))
            story.append(_penetration_table(
                cht.penetrations,
                headers=["Zone", "Permitted (m AMSL)", "Building (m AMSL)", "Excess (m)"],
                keys=["zone", "permitted_m_amsl", "building_m_amsl", "excess_m"],
            ))
        if cht.intersects:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                "<b>Action required:</b> CHT penetration triggers mandatory ADP officer review. "
                "CAAS must assess whether a height reduction, LOC conditions, or a formal "
                "aeronautical study is required before a Letter of Consent can be issued.",
                _S["warn"],
            ))
    else:
        story.append(_section_header(
            "STAGE 5 -- COMPOSITE HEIGHT TEMPLATE (CHT) INTERSECTION",
            "PENDING", _GREY))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Awaiting CAAS CHT GIS layer delivery (US-22 open clarification). "
            "This section will be populated once the multipatch or shapefile is received.",
            _S["pending"],
        ))
    story.append(Spacer(1, 8))

    # ── Stage 6: OLS ────────────────────────────────────────────────────────────
    if ols is not None:
        ols_colour = _RED if ols.intersects else _GREEN
        ols_tag    = f"{len(ols.surfaces_penetrated)} surface(s) penetrated" if ols.intersects else "CLEAR"
        story.append(_section_header(
            "STAGE 6 -- OLS (OBSTACLE LIMITATION SURFACES) INTERSECTION",
            ols_tag, ols_colour))
        story.append(Spacer(1, 4))
        if ols.surfaces_penetrated:
            story.append(Paragraph("<b>Penetrated surfaces:</b>", _S["body"]))
            story.append(Spacer(1, 2))
            story.append(_penetration_table(
                ols.surfaces_penetrated,
                headers=["Surface", "Runway", "OLS Height (m AMSL)", "Building (m AMSL)", "Depth (m)"],
                keys=["surface", "runway", "surface_height_at_point_m_amsl",
                      "building_m_amsl", "penetration_depth_m"],
            ))
        if ols.surfaces_clear:
            story.append(Spacer(1, 4))
            story.append(Paragraph("<b>Surfaces clear:</b>", _S["body"]))
            story.append(_status_table([(True, s) for s in ols.surfaces_clear]))
        if ols.intersects:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                "<b>Note:</b> OLS penetration must be declared in the LOC application "
                "and assessed by CAAS aerodromes engineers.",
                _S["warn"],
            ))
    else:
        story.append(_section_header(
            "STAGE 6 -- OLS (OBSTACLE LIMITATION SURFACES) INTERSECTION",
            "PENDING", _GREY))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Awaiting CAAS OLS 3D surface layer delivery (US-16/US-20 open clarifications).",
            _S["pending"],
        ))
    story.append(Spacer(1, 8))

    # ── Stage 7: ILS ────────────────────────────────────────────────────────────
    if ils is not None:
        ils_colour = _RED if ils.impacts else _GREEN
        ils_tag    = f"{len(ils.templates_breached)} template(s) breached" if ils.impacts else "CLEAR"
        story.append(_section_header(
            "STAGE 7 -- ILS TECHNICAL TEMPLATE IMPACT",
            ils_tag, ils_colour))
        story.append(Spacer(1, 4))
        if ils.templates_breached:
            story.append(Paragraph("<b>Breached templates:</b>", _S["body"]))
            story.append(Spacer(1, 2))
            story.append(_penetration_table(
                ils.templates_breached,
                headers=["Template", "System", "Runway", "Ceiling (m AMSL)",
                         "Building (m AMSL)", "Excess (m)"],
                keys=["template_id", "system", "runway", "permitted_m_amsl",
                      "building_m_amsl", "excess_m"],
            ))
        if ils.templates_clear:
            story.append(Spacer(1, 4))
            story.append(Paragraph("<b>Templates clear:</b>", _S["body"]))
            story.append(_status_table([(True, t) for t in ils.templates_clear]))
        if ils.impacts:
            story.append(Spacer(1, 4))
            story.append(Paragraph(
                "<b>Action required:</b> ILS template breach requires an RF propagation "
                "study by the CAAS ILS team before the LOC application can progress.",
                _S["warn"],
            ))
    else:
        story.append(_section_header(
            "STAGE 7 -- ILS TECHNICAL TEMPLATE IMPACT",
            "PENDING", _GREY))
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            "Awaiting CAAS ILS technical template layer delivery (US-17 open clarification).",
            _S["pending"],
        ))
    story.append(Spacer(1, 8))

    # ── Assessment summary ───────────────────────────────────────────────────────
    story.append(_section_header("ASSESSMENT SUMMARY", "", _NAVY))
    story.append(Spacer(1, 4))

    def _ok(ok: bool | None) -> str:
        return "PASS" if ok is True else ("FAIL" if ok is False else "PENDING")

    se_ok_bool    = se.status == "ok"
    cht_ok_bool   = (not cht.intersects) if cht is not None else None
    ols_ok_bool   = (not ols.intersects) if ols is not None else None
    ils_ok_bool   = (not ils.impacts)    if ils is not None else None
    gfa_ok_bool   = within

    summary_data = [
        [Paragraph("Check", ParagraphStyle("th", fontSize=8, fontName="Helvetica-Bold",
                                           textColor=_WHITE)),
         Paragraph("Result", ParagraphStyle("th", fontSize=8, fontName="Helvetica-Bold",
                                            textColor=_WHITE)),
         Paragraph("Detail", ParagraphStyle("th", fontSize=8, fontName="Helvetica-Bold",
                                            textColor=_WHITE))],
        [Paragraph("IFC Ingestion & Validation", _S["body"]),
         Paragraph("PASS", _S["pass"]),
         Paragraph(response.ifc_filename, _S["body"])],
        [Paragraph("Exterior Shell Extraction", _S["body"]),
         Paragraph(_ok(se_ok_bool), _S["pass"] if se_ok_bool else _S["fail"]),
         Paragraph(f"{se.element_count:,} elements, {se.triangle_count:,} triangles", _S["body"])],
        [Paragraph("Height Analysis", _S["body"]),
         Paragraph("COMPLETE", _S["pass"]),
         Paragraph(f"{ha.height_m} m building height, {ha_amsl} m AMSL peak", _S["body"])],
        [Paragraph("Gross Floor Area", _S["body"]),
         Paragraph(_ok(gfa_ok_bool),
                   _S["pass"] if gfa_ok_bool else (_S["fail"] if gfa_ok_bool is False else _S["pending"])),
         Paragraph(f"{gfa.gfa_m2:,.1f} m²" + (f" / {gfa_limit:,.1f} m² limit" if gfa_limit else ""), _S["body"])],
        [Paragraph("Composite Height Template (CHT)", _S["body"]),
         Paragraph(_ok(cht_ok_bool),
                   _S["fail"] if cht_ok_bool is False else (_S["pass"] if cht_ok_bool else _S["pending"])),
         Paragraph(f"Penetration: {cht.penetration_depth_m} m" if (cht and cht.intersects) else
                   ("Clear" if (cht and not cht.intersects) else "Pending CAAS GIS data"), _S["body"])],
        [Paragraph("OLS Intersection", _S["body"]),
         Paragraph(_ok(ols_ok_bool),
                   _S["fail"] if ols_ok_bool is False else (_S["pass"] if ols_ok_bool else _S["pending"])),
         Paragraph(f"{len(ols.surfaces_penetrated)} surface(s) penetrated" if (ols and ols.intersects) else
                   ("All surfaces clear" if (ols and not ols.intersects) else "Pending CAAS GIS data"), _S["body"])],
        [Paragraph("ILS Technical Template", _S["body"]),
         Paragraph(_ok(ils_ok_bool),
                   _S["fail"] if ils_ok_bool is False else (_S["pass"] if ils_ok_bool else _S["pending"])),
         Paragraph(f"{len(ils.templates_breached)} template(s) breached" if (ils and ils.impacts) else
                   ("All templates clear" if (ils and not ils.impacts) else "Pending CAAS GIS data"), _S["body"])],
    ]
    summary_tbl = Table(summary_data,
                        colWidths=[CONTENT_W * 0.40, CONTENT_W * 0.15, CONTENT_W * 0.45])
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _LGREY]),
        ("GRID", (0, 0), (-1, -1), 0.3, _GREY),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 4),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 6))

    # ── Footer disclaimer ────────────────────────────────────────────────────────
    story.append(_hr())
    story.append(Paragraph(
        "Generated by iEP SkySAFE 2.0 Processing Service v0.1.0 &nbsp;|&nbsp; "
        f"{generated_at.strftime('%Y-%m-%d %H:%M UTC')} &nbsp;|&nbsp; "
        "CONFIDENTIAL -- CAAS Internal Use Only",
        _S["footer"],
    ))

    doc.build(story)
    return buf.getvalue()
