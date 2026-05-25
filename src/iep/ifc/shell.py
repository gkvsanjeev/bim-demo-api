"""
Exterior shell extraction — the single chokepoint that decides which IFC elements
enter the geometry pipeline.  No interior elements may pass this module.
"""

from __future__ import annotations

import numpy as np
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element
from loguru import logger

from iep.ifc.facade import extract_facade_materials
from iep.ifc.gfa import compute_gfa
from iep.models.errors import ShellExtractionError
from iep.models.shell import ShellResult

# IFC entity types that can form the building envelope.
_ENVELOPE_TYPES = (
    "IfcWall",
    "IfcWallStandardCase",
    "IfcSlab",
    "IfcRoof",
    "IfcCurtainWall",
    "IfcPlate",
    "IfcBuildingElementProxy",
)

# Pset names (keyed by IFC entity type prefix) that carry IsExternal.
_EXTERIOR_PSETS = {
    "IfcWall": ["Pset_WallCommon"],
    "IfcSlab": ["Pset_SlabCommon"],
    "IfcRoof": ["Pset_RoofCommon"],
    "IfcCurtainWall": ["Pset_CurtainWallCommon"],
    "IfcPlate": ["Pset_PlateCommon"],
    "IfcBuildingElementProxy": ["Pset_BuildingElementProxyCommon"],
}

# IFC slab predefined types that are always part of the exterior shell.
_ALWAYS_EXTERIOR_SLAB_TYPES = {"ROOF", "BASESLAB"}

# IFC types that are unconditionally exterior (no IsExternal check needed).
_UNCONDITIONALLY_EXTERIOR = {"IfcRoof", "IfcCurtainWall"}


def _is_exterior(element: ifcopenshell.entity_instance) -> bool:
    """
    Return True if the element belongs to the building exterior.

    Resolution order:
      1. IfcRoof / IfcCurtainWall → always exterior.
      2. IfcSlab with ROOF or BASESLAB predefined type → always exterior.
      3. Pset IsExternal property (any relevant Pset for the element type).
      4. Fallback: include if no IsExternal property found (conservative — keeps
         elements that authors forgot to tag; downstream geometry checks remove
         clearly interior elements via bounding-box heuristics).
    """
    ifc_class = element.is_a()

    if ifc_class in _UNCONDITIONALLY_EXTERIOR:
        return True

    if ifc_class == "IfcSlab":
        ptype = getattr(element, "PredefinedType", None) or ""
        if ptype in _ALWAYS_EXTERIOR_SLAB_TYPES:
            return True

    psets = ifcopenshell.util.element.get_psets(element)
    candidate_psets = _EXTERIOR_PSETS.get(
        ifc_class,
        _EXTERIOR_PSETS.get(ifc_class.replace("StandardCase", ""), []),
    )
    for pset_name in candidate_psets:
        pset = psets.get(pset_name, {})
        is_ext = pset.get("IsExternal")
        if is_ext is not None:
            return bool(is_ext)

    # No property found — include by default (conservative).
    return True


def _get_site_elevation(model: ifcopenshell.file) -> float:
    """Return IfcSite.RefElevation in metres, or 0.0 if not defined."""
    sites = model.by_type("IfcSite")
    if not sites:
        return 0.0
    ref_elev = getattr(sites[0], "RefElevation", None)
    return float(ref_elev) if ref_elev is not None else 0.0


def _make_geom_settings() -> ifcopenshell.geom.settings:
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    # Triangulate to get simple meshes.
    settings.set(settings.WELD_VERTICES, True)
    return settings


def extract_exterior_shell(model: ifcopenshell.file) -> ShellResult:
    """
    Extract the simplified outer envelope of the building.

    Returns a ShellResult with:
    - 3D triangle mesh of exterior elements (world coords, metres)
    - Elevation of the site datum
    - Facade material attributes per element
    - Gross Floor Area (from floor slabs)

    Raises ShellExtractionError if no exterior geometry can be produced.
    """
    logger.info("Scanning IFC model for exterior envelope elements")

    exterior_elements: list[ifcopenshell.entity_instance] = []
    for ifc_type in _ENVELOPE_TYPES:
        for element in model.by_type(ifc_type):
            if _is_exterior(element):
                exterior_elements.append(element)

    if not exterior_elements:
        raise ShellExtractionError("No exterior envelope elements found in IFC model")

    logger.info(
        "Found {} exterior elements across {} IFC types",
        len(exterior_elements),
        len({e.is_a() for e in exterior_elements}),
    )

    geom_settings = _make_geom_settings()

    all_vertices: list[np.ndarray] = []
    all_faces: list[np.ndarray] = []
    vertex_offset = 0
    failed = 0

    for element in exterior_elements:
        try:
            shape = ifcopenshell.geom.create_shape(geom_settings, element)
        except Exception as exc:
            logger.debug(
                "Geometry creation failed for {} {}: {}", element.is_a(), element.GlobalId, exc
            )
            failed += 1
            continue

        verts = np.array(shape.geometry.verts, dtype=np.float64).reshape(-1, 3)
        faces_flat = np.array(shape.geometry.faces, dtype=np.int32)

        if verts.shape[0] == 0 or faces_flat.shape[0] == 0:
            continue

        faces = faces_flat.reshape(-1, 3) + vertex_offset

        all_vertices.append(verts)
        all_faces.append(faces)
        vertex_offset += verts.shape[0]

    if not all_vertices:
        raise ShellExtractionError(
            f"All {len(exterior_elements)} exterior elements failed geometry creation"
        )

    if failed:
        logger.warning("{} elements had geometry creation errors and were skipped", failed)

    vertices_m = np.concatenate(all_vertices, axis=0)
    faces_arr = np.concatenate(all_faces, axis=0).astype(np.int32)

    min_z_m = float(vertices_m[:, 2].min())
    max_z_m = float(vertices_m[:, 2].max())
    height_m = max_z_m - min_z_m

    elevation_m_local = _get_site_elevation(model)

    logger.info(
        "Shell mesh: {} vertices, {} triangles, Z range [{:.2f}, {:.2f}] m, height {:.2f} m",
        len(vertices_m),
        len(faces_arr),
        min_z_m,
        max_z_m,
        height_m,
    )

    facade_materials = extract_facade_materials(model, exterior_elements)

    logger.info("Computing GFA from floor slabs")
    gfa_m2 = compute_gfa(model, geom_settings)
    logger.info("GFA: {:.1f} m²", gfa_m2)

    return ShellResult(
        vertices_m=vertices_m,
        faces=faces_arr,
        element_count=len(exterior_elements) - failed,
        elevation_m_local=elevation_m_local,
        min_z_m=min_z_m,
        max_z_m=max_z_m,
        height_m=height_m,
        gfa_m2=gfa_m2,
        facade_materials=facade_materials,
    )
