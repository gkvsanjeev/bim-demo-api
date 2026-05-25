"""Gross Floor Area computation from IFC floor slabs."""

from __future__ import annotations

import numpy as np
import ifcopenshell
import ifcopenshell.geom

# IFC predefined types treated as floor slabs (not roof)
_FLOOR_SLAB_TYPES = {"FLOOR", "BASESLAB", "LANDING", ""}

# Only upward-facing triangles contribute to floor area (normal.z > threshold).
# This filters out side faces and the bottom surface of the slab.
_MIN_UPWARD_NORMAL_Z = 0.5


def _triangle_projected_areas(
    verts: np.ndarray, faces: np.ndarray
) -> np.ndarray:
    """
    Return the signed XY-projected area for every triangle.

    XY-projected area = 0.5 * |cross(v1-v0, v2-v0)|_z
    Positive when the triangle faces up (normal.z > 0).
    """
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    e1 = v1 - v0
    e2 = v2 - v0
    cross_z = e1[:, 0] * e2[:, 1] - e1[:, 1] * e2[:, 0]
    return 0.5 * cross_z  # positive = upward-facing


def compute_gfa(
    model: ifcopenshell.file,
    geom_settings: ifcopenshell.geom.settings,
) -> float:
    """
    Compute Gross Floor Area (m²) by summing the horizontal area of the
    top surface of each IfcSlab floor element across all storeys.

    Only upward-facing triangles (normal.z > 0.5) are counted, so the
    bottom surface and side faces of each slab are excluded.  Slabs on
    different storeys are summed independently (not unioned), so the total
    reflects the full multi-storey GFA rather than just the footprint.

    Returns 0.0 if no floor slabs are found.
    """
    total_area = 0.0

    for slab in model.by_type("IfcSlab"):
        ptype = getattr(slab, "PredefinedType", None) or ""
        if ptype not in _FLOOR_SLAB_TYPES:
            continue  # skip ROOF etc.

        try:
            shape = ifcopenshell.geom.create_shape(geom_settings, slab)
        except Exception:
            continue

        verts = np.array(shape.geometry.verts, dtype=np.float64).reshape(-1, 3)
        faces_flat = np.array(shape.geometry.faces, dtype=np.int32)
        if verts.shape[0] == 0 or faces_flat.shape[0] == 0:
            continue

        faces = faces_flat.reshape(-1, 3)
        proj_areas = _triangle_projected_areas(verts, faces)

        # Keep only upward-facing triangles.
        upward_mask = proj_areas > 0
        total_area += float(proj_areas[upward_mask].sum())

    return total_area
