"""
iEP SkySAFE 2.0 -- Aviation Safety Analysis Result
====================================================
Prints a structured console report of the BIM processing pipeline:
  1. IFC ingestion & validation
  2. Exterior shell extraction
  3. Height analysis
  4. Gross Floor Area (GFA) check
  5. Composite Height Template (CHT) intersection
  6. OLS (Obstacle Limitation Surfaces) intersection
  7. ILS (Instrument Landing System) technical template impact

Stages 1-4 reflect the implemented iEP modules.
Stages 5-7 use representative simulated outputs (pending CAAS GIS layer delivery).

For a PDF report, call POST /processing/analysis-report via the FastAPI service.

Run:
    uv run python scripts/analysis_result.py
"""

from __future__ import annotations

import json
import textwrap
from datetime import datetime, timezone

# ------------------------------------------------------------------------------
# Formatting helpers
# ------------------------------------------------------------------------------

WIDTH = 70
THIN  = "-" * WIDTH
THICK = "=" * WIDTH


def _header(title: str) -> None:
    pad = (WIDTH - len(title) - 2) // 2
    print()
    print("+" + THICK + "+")
    print("|" + " " * pad + title + " " * (WIDTH - pad - len(title)) + "|")
    print("+" + THICK + "+")
    print()


def _section(title: str, tag: str = "") -> None:
    label = f"  {title}"
    if tag:
        label += f"  [{tag}]"
    print()
    print(THIN)
    print(label)
    print(THIN)


def _field(label: str, value: object, unit: str = "", indent: int = 4) -> None:
    prefix = " " * indent
    val_str = str(value)
    if unit:
        val_str += f" {unit}"
    print(f"{prefix}{label:<38}{val_str}")


def _status(ok: bool, text: str = "", indent: int = 4) -> None:
    icon = "[PASS]" if ok else "[FAIL]"
    colour_on  = "\033[92m" if ok else "\033[91m"
    colour_off = "\033[0m"
    prefix = " " * indent
    print(f"{prefix}{colour_on}{icon}{colour_off}  {text}")


def _warn(text: str, indent: int = 4) -> None:
    prefix = " " * indent
    print(f"{prefix}\033[93m[WARN]\033[0m  {text}")


def _bullet(text: str, indent: int = 6) -> None:
    prefix = " " * indent
    print(f"{prefix}*  {text}")


def _note(text: str, indent: int = 4) -> None:
    prefix = " " * indent
    wrapped = textwrap.fill(text, width=WIDTH - indent - 4,
                            subsequent_indent=" " * (indent + 4))
    print(f"{prefix}NOTE: {wrapped}")


# ------------------------------------------------------------------------------
# Demo data --representative Singapore high-rise commercial tower
# (Values calibrated against a 30-storey building in the Changi approach corridor)
# ------------------------------------------------------------------------------

REQUEST = {
    "application_ref": "SKY-2025-00847",
    "ifc_filename":    "proposal_sky2025_00847_corenet.ifc",
}

# -- IFC ingestion --------------------------------------------------------------
IFC_META = {
    "schema":        "IFC4",
    "sg_profile":    "IFC+SG v1.0",
    "file_size_mb":  18.4,
    "ifc_project":   "Proposed Commercial Tower at Lot 12345X MK01",
    "author":        "BuildArch Consultants Pte Ltd",
    "timestamp":     "2025-03-14T09:22:01+08:00",
}

# -- Shell extraction -----------------------------------------------------------
SHELL = {
    "status":         "ok",
    "element_count":  312,
    "vertex_count":   28_450,
    "triangle_count": 54_918,
    "types_found": [
        ("IfcWall",          148),
        ("IfcWallStandardCase", 62),
        ("IfcCurtainWall",    67),
        ("IfcSlab",           24),
        ("IfcRoof",            6),
        ("IfcPlate",           5),
    ],
    "interior_excluded": 1_204,
}

# -- Height analysis ------------------------------------------------------------
HEIGHT = {
    "elevation_m_local":   3.2,    # IfcSite.RefElevation above SVY21 datum
    "min_z_m":             0.0,    # ground floor slab soffit
    "max_z_m":            98.35,   # roof apex
    "height_m":           98.35,
    "height_m_amsl":      101.55,  # max_z + elevation_m_local
    "storey_count":        30,
}

# -- GFA -----------------------------------------------------------------------
GFA = {
    "gfa_m2":     45_230.0,
    "limit_m2":   60_000.0,
    "within_limit": True,
}

# -- Facade materials ----------------------------------------------------------
MATERIALS = [
    {"name": "Aluminium Panel Cladding",      "element_count": 67,  "reflectivity_class": "HIGH"},
    {"name": "Reinforced Concrete",           "element_count": 148, "reflectivity_class": "MEDIUM"},
    {"name": "Structural Glass (Low-E)",      "element_count": 62,  "reflectivity_class": "LOW"},
    {"name": "Steel Plate",                   "element_count": 5,   "reflectivity_class": "HIGH"},
    {"name": "Fibre-Cement Board",            "element_count": 24,  "reflectivity_class": "LOW"},
    {"name": "Precast Architectural Concrete","element_count": 6,   "reflectivity_class": "MEDIUM"},
]

# -- Composite Height Template (CHT) ------------------------------------------
CHT = {
    "intersects": True,
    "max_permitted_height_m_amsl": 88.85,
    "building_peak_m_amsl":        101.55,
    "penetration_depth_m":         12.70,
    "penetrations": [
        {
            "zone":           "CHT Zone A --Primary Obstacle Limitation",
            "permitted_m_amsl": 88.85,
            "building_m_amsl":  101.55,
            "excess_m":         12.70,
        },
    ],
}

# -- OLS (Obstacle Limitation Surfaces) ---------------------------------------
OLS = {
    "intersects": True,
    "surfaces_penetrated": [
        {
            "surface":     "Transitional Surface",
            "runway":      "RWY 02L/20R",
            "aerodrome":   "Singapore Changi Airport (WSSS)",
            "penetration_depth_m": 7.42,
            "building_m_amsl":     101.55,
            "surface_height_at_point_m_amsl": 94.13,
            "lateral_offset_m": 284.0,
        },
    ],
    "surfaces_clear": [
        "Approach Surface",
        "Take-off Climb Surface",
        "Inner Horizontal Surface",
        "Conical Surface",
        "Outer Horizontal Surface",
    ],
}

# -- ILS technical template ----------------------------------------------------
ILS = {
    "impacts":            True,
    "templates_breached": [
        {
            "template_id":    "ILS-WSSS-02L-LOC",
            "system":         "Localiser (LOC)",
            "runway":         "RWY 02L",
            "aerodrome":      "Singapore Changi Airport (WSSS)",
            "type":           "Height template breach",
            "permitted_m_amsl": 85.00,
            "building_m_amsl":  101.55,
            "excess_m":         16.55,
            "azimuth_from_antenna_deg": 312.4,
            "distance_from_antenna_m":  1_840.0,
        },
    ],
    "templates_clear": [
        "ILS-WSSS-02L-GP",
        "ILS-WSSS-20R-LOC",
        "ILS-WSSS-20R-GP",
    ],
}

# -- Full structured response (US-12 / US-20 schema) --------------------------
FULL_RESPONSE = {
    "application_ref": REQUEST["application_ref"],
    "ifc_filename":    REQUEST["ifc_filename"],
    "shell_extraction": {
        "status":         SHELL["status"],
        "element_count":  SHELL["element_count"],
        "vertex_count":   SHELL["vertex_count"],
        "triangle_count": SHELL["triangle_count"],
    },
    "height_analysis": {
        "elevation_m_local": HEIGHT["elevation_m_local"],
        "min_z_m":           HEIGHT["min_z_m"],
        "max_z_m":           HEIGHT["max_z_m"],
        "height_m":          HEIGHT["height_m"],
    },
    "gfa": {
        "gfa_m2":       GFA["gfa_m2"],
        "limit_m2":     GFA["limit_m2"],
        "within_limit": GFA["within_limit"],
    },
    "facade_materials": {
        "unique_material_count": len(MATERIALS),
        "materials": [
            {"name": m["name"], "element_count": m["element_count"]}
            for m in MATERIALS
        ],
    },
    "assessments": {
        "composite_height": {
            "intersects":              CHT["intersects"],
            "max_permitted_m_amsl":    CHT["max_permitted_height_m_amsl"],
            "building_peak_m_amsl":    CHT["building_peak_m_amsl"],
            "penetration_depth_m":     CHT["penetration_depth_m"],
            "penetrations":            CHT["penetrations"],
        },
        "ols": {
            "intersects":          OLS["intersects"],
            "surfaces_penetrated": OLS["surfaces_penetrated"],
            "surfaces_clear":      OLS["surfaces_clear"],
        },
        "ils": {
            "impacts":            ILS["impacts"],
            "templates_breached": ILS["templates_breached"],
            "templates_clear":    ILS["templates_clear"],
        },
    },
    "errors": [],
    "_generated_at": datetime.now(timezone.utc).isoformat(),
    "_pipeline_version": "0.1.0",
}


# ------------------------------------------------------------------------------
# Presentation
# ------------------------------------------------------------------------------

def main() -> None:
    _header("iEP SkySAFE 2.0 -- Aviation Safety Assessment Demo")

    # -- Request ---------------------------------------------------------------
    _section("API REQUEST", "POST /processing/extract-shell")
    _field("Application reference",  REQUEST["application_ref"])
    _field("IFC filename",           REQUEST["ifc_filename"])
    _field("Invoked at",             datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    # -- Stage 1: IFC Ingestion ------------------------------------------------
    _section("STAGE 1 --IFC INGESTION & VALIDATION", "(ok) PASS")
    _status(True,  f"File located on SFTP landing directory")
    _status(True,  f"IFC schema: {IFC_META['schema']} / {IFC_META['sg_profile']}")
    _status(True,  f"File size: {IFC_META['file_size_mb']} MB")
    print()
    _field("Project name",   IFC_META["ifc_project"])
    _field("Author",         IFC_META["author"])
    _field("File timestamp", IFC_META["timestamp"])

    # -- Stage 2: Exterior Shell Extraction -----------------------------------
    _section("STAGE 2 --EXTERIOR SHELL EXTRACTION", "(ok) PASS")
    _status(True,  f"{SHELL['element_count']} exterior envelope elements extracted")
    _status(True,  f"{SHELL['interior_excluded']} interior elements excluded (chokepoint filter)")
    print()
    print("    Element breakdown:")
    for ifc_type, count in SHELL["types_found"]:
        _field(f"  {ifc_type}", count, "elements", indent=6)
    print()
    _field("Mesh vertices",    f"{SHELL['vertex_count']:,}")
    _field("Mesh triangles",   f"{SHELL['triangle_count']:,}")

    # -- Stage 3: Height Analysis ----------------------------------------------
    _section("STAGE 3 --HEIGHT ANALYSIS", "(ok) COMPLETE")
    _field("Site elevation (IfcSite.RefElevation)", HEIGHT["elevation_m_local"], "m (local datum)")
    _field("Lowest point (ground slab soffit)",     HEIGHT["min_z_m"],            "m")
    _field("Highest point (roof apex)",             HEIGHT["max_z_m"],            "m (local)")
    _field("Building height",                       HEIGHT["height_m"],            "m")
    _field("Peak height above mean sea level",      HEIGHT["height_m_amsl"],      "m AMSL  <<used for all assessments")
    _field("Number of storeys",                     HEIGHT["storey_count"])

    # -- Stage 4: GFA ---------------------------------------------------------
    _section("STAGE 4 --GROSS FLOOR AREA (GFA)", "(ok) WITHIN LIMIT")
    _field("Proposed GFA",  f"{GFA['gfa_m2']:,.1f}",  "m2")
    _field("Site GFA limit", f"{GFA['limit_m2']:,.1f}", "m2")
    _field("Utilisation",   f"{GFA['gfa_m2'] / GFA['limit_m2'] * 100:.1f}", "%  (within limit)")
    _status(True, "GFA is within the pre-configured site limit")

    # -- Stage 4b: Facade Materials -------------------------------------------
    _section("STAGE 4b --FACADE MATERIAL SURVEY")
    _field("Unique material types found", len(MATERIALS))
    print()
    print(f"    {'Material':<42} {'Elements':>8}  {'Radar Reflectivity'}")
    print(f"    {'-' * 42} {'-' * 8}  {'-' * 19}")
    for m in MATERIALS:
        ref_label = m["reflectivity_class"]
        colour = {"HIGH": "\033[91m", "MEDIUM": "\033[93m", "LOW": "\033[92m"}.get(ref_label, "")
        colour_off = "\033[0m"
        print(f"    {m['name']:<42} {m['element_count']:>8}  {colour}{ref_label}{colour_off}")
    _note(
        "Aluminium cladding and steel plate carry HIGH radar reflectivity. "
        "Combined with building height, these materials are flagged for the radar "
        "line-of-sight assessment (US-18, pending CAAS radar layer delivery)."
    )

    # -- Stage 5: CHT ---------------------------------------------------------
    _section("STAGE 5 --COMPOSITE HEIGHT TEMPLATE (CHT) INTERSECTION", "(!)  PENETRATION")
    _warn("Building PENETRATES the Composite Height Template")
    print()
    _field("Max permitted height (CHT)",  CHT["max_permitted_height_m_amsl"], "m AMSL")
    _field("Building peak height",        CHT["building_peak_m_amsl"],         "m AMSL")
    _field("Penetration depth",           CHT["penetration_depth_m"],           "m  <<exceeds template")
    print()
    for p in CHT["penetrations"]:
        print(f"    Zone:      {p['zone']}")
        print(f"    Permitted: {p['permitted_m_amsl']} m AMSL   |   Proposed: {p['building_m_amsl']} m AMSL   |   Excess: {p['excess_m']} m")
    _note(
        "CHT penetration triggers mandatory further review by ADP officers. "
        "CAAS must assess whether a height reduction, LOC conditions, or a formal "
        "aeronautical study is required before a Letter of Consent can be issued."
    )

    # -- Stage 6: OLS ---------------------------------------------------------
    _section("STAGE 6 --OLS (OBSTACLE LIMITATION SURFACES) INTERSECTION", "(!)  PENETRATION")
    _warn("Building PENETRATES 1 of 6 OLS surfaces")
    print()
    for s in OLS["surfaces_penetrated"]:
        print(f"    Surface:              {s['surface']}")
        print(f"    Runway / Aerodrome:   {s['runway']}  -- {s['aerodrome']}")
        print(f"    Lateral offset:       {s['lateral_offset_m']:.0f} m from runway centreline")
        print(f"    OLS height at point:  {s['surface_height_at_point_m_amsl']:.2f} m AMSL")
        print(f"    Building peak:        {s['building_m_amsl']:.2f} m AMSL")
        print(f"    Penetration depth:    {s['penetration_depth_m']:.2f} m")
    print()
    print("    Surfaces clear (building below OLS):")
    for surf in OLS["surfaces_clear"]:
        _status(True, surf)
    _note(
        "Penetration of the Transitional Surface does not automatically prevent "
        "approval, but must be declared in the LOC application and assessed by "
        "CAAS aerodromes engineers. The Transitional Surface protects aircraft "
        "during the initial go-around phase."
    )

    # -- Stage 7: ILS ---------------------------------------------------------
    _section("STAGE 7 --ILS TECHNICAL TEMPLATE IMPACT", "(!)  BREACH")
    _warn("Building BREACHES the ILS height template for 1 of 4 checked systems")
    print()
    for t in ILS["templates_breached"]:
        print(f"    Template ID:          {t['template_id']}")
        print(f"    System:               {t['system']}  -- {t['runway']}")
        print(f"    Aerodrome:            {t['aerodrome']}")
        print(f"    Distance from antenna:{t['distance_from_antenna_m']:,.0f} m")
        print(f"    Azimuth from antenna: {t['azimuth_from_antenna_deg']} deg")
        print(f"    Template ceiling:     {t['permitted_m_amsl']:.2f} m AMSL")
        print(f"    Building peak:        {t['building_m_amsl']:.2f} m AMSL")
        print(f"    Excess above template:{t['excess_m']:.2f} m")
    print()
    print("    ILS templates clear:")
    for tmpl in ILS["templates_clear"]:
        _status(True, tmpl)
    _note(
        "LOC antenna sensitivity is directly proportional to distance. At 1,840 m "
        "from the antenna, a 16.55 m exceedance is classified as a significant "
        "impact. CAAS ILS team must conduct a radio frequency (RF) propagation study "
        "before the LOC application can progress."
    )

    # -- Summary ---------------------------------------------------------------
    _section("ASSESSMENT SUMMARY")
    print()
    _status(True,  "IFC ingestion & schema validation       PASS")
    _status(True,  "Exterior shell extraction               PASS   (312 elements, 54,918 triangles)")
    _status(True,  "Height analysis                         COMPLETE  (98.35 m, 101.55 m AMSL)")
    _status(True,  "GFA check                               PASS   (45,230 m2 / 60,000 m2 limit)")
    _status(False, "Composite Height Template               FAIL   (penetration: 12.70 m)")
    _status(False, "OLS intersection                        FAIL   (Transitional surface breached by 7.42 m)")
    _status(False, "ILS technical template                  FAIL   (LOC RWY 02L breached by 16.55 m)")
    print()
    _warn(
        "3 of 7 aviation safety checks require CAAS review before "
        "a Letter of Consent (LOC) can be issued."
    )

    # -- Full JSON -------------------------------------------------------------
    _section("STRUCTURED JSON RESPONSE  (SkySAFE-parseable payload)")
    print()
    print(json.dumps(FULL_RESPONSE, indent=2, ensure_ascii=False))

    print()
    print(THIN)
    _note(
        "Stages 5-7 use representative simulated outputs. "
        "Live results require delivery of the CAAS GIS layers (CHT multipatch, OLS 3D surfaces, "
        "ILS technical template shapefiles) per US-16/17/22 open clarifications."
    )
    print(THIN)
    print()


if __name__ == "__main__":
    main()
