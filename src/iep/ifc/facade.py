"""Facade material attribute extraction from exterior IFC elements."""

from __future__ import annotations

from typing import TYPE_CHECKING

import ifcopenshell
import ifcopenshell.util.element

from iep.models.shell import FacadeMaterial

if TYPE_CHECKING:
    pass

# Thickness attribute in IfcMaterialLayer is LayerThickness (IFC2x3) or Thickness (IFC4).
_LAYER_THICKNESS_ATTRS = ("Thickness", "LayerThickness")


def _layer_thickness_m(layer: ifcopenshell.entity_instance) -> float | None:
    """Return material layer thickness in metres, or None if not set."""
    for attr in _LAYER_THICKNESS_ATTRS:
        val = getattr(layer, attr, None)
        if val is not None:
            return float(val)
    return None


def _material_name(material: ifcopenshell.entity_instance) -> str:
    return getattr(material, "Name", None) or ""


def extract_facade_materials(
    model: ifcopenshell.file,
    exterior_elements: list[ifcopenshell.entity_instance],
) -> list[FacadeMaterial]:
    """
    Return one FacadeMaterial per exterior element.

    Resolution order:
      1. IfcMaterialLayerSetUsage → outermost layer material + thickness
      2. IfcMaterialLayerSet → first layer
      3. IfcMaterialList → first material
      4. IfcMaterial → direct assignment
    """
    results: list[FacadeMaterial] = []

    for element in exterior_elements:
        material_name, thickness_m = _resolve_material(element)
        results.append(
            FacadeMaterial(
                element_global_id=element.GlobalId,
                element_type=element.is_a(),
                material_name=material_name,
                thickness_m=thickness_m,
            )
        )

    return results


def _resolve_material(
    element: ifcopenshell.entity_instance,
) -> tuple[str, float | None]:
    """Return (material_name, thickness_m) for a single element."""
    associations = ifcopenshell.util.element.get_material(element)
    if associations is None:
        return ("", None)

    ifc_type = associations.is_a()

    if ifc_type == "IfcMaterialLayerSetUsage":
        layer_set = associations.ForLayerSet
        layers = layer_set.MaterialLayers if layer_set else []
        if layers:
            # IFC spec: DirectionSense POSITIVE → layers run outward from reference plane;
            # take the first layer as the outermost façade layer.
            outer = layers[0]
            mat = outer.Material
            return (
                _material_name(mat) if mat else "",
                _layer_thickness_m(outer),
            )

    if ifc_type == "IfcMaterialLayerSet":
        layers = associations.MaterialLayers
        if layers:
            outer = layers[0]
            mat = outer.Material
            return (
                _material_name(mat) if mat else "",
                _layer_thickness_m(outer),
            )

    if ifc_type == "IfcMaterialList":
        materials = associations.Materials
        if materials:
            return (_material_name(materials[0]), None)

    if ifc_type == "IfcMaterial":
        return (_material_name(associations), None)

    return ("", None)
