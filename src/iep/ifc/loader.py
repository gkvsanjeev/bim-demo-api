from pathlib import Path

import ifcopenshell

from iep.models.errors import IFCLoadError


def load_ifc(path: Path) -> ifcopenshell.file:
    """Open an IFC file from disk, raising IFCLoadError if it cannot be read."""
    if not path.exists():
        raise IFCLoadError(f"IFC file not found: {path}")
    try:
        model = ifcopenshell.open(str(path))
    except Exception as exc:
        raise IFCLoadError(f"Failed to open IFC file {path.name}: {exc}") from exc
    if model is None:
        raise IFCLoadError(f"ifcopenshell returned None for {path.name}")
    return model
