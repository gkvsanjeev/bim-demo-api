"""
CLI: iep-extract-shell <ifc_file>

Loads an IFC file, extracts the exterior shell, and prints a JSON summary.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from loguru import logger

from iep.ifc.loader import load_ifc
from iep.ifc.shell import extract_exterior_shell
from iep.models.errors import IFCLoadError, ShellExtractionError


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: iep-extract-shell <path/to/file.ifc>", file=sys.stderr)
        sys.exit(1)

    ifc_path = Path(sys.argv[1])

    logger.info("Loading {}", ifc_path.name)
    try:
        model = load_ifc(ifc_path)
    except IFCLoadError as exc:
        logger.error("IFC load failed: {}", exc)
        sys.exit(1)

    logger.info("Extracting exterior shell")
    try:
        result = extract_exterior_shell(model)
    except ShellExtractionError as exc:
        logger.error("Shell extraction failed: {}", exc)
        sys.exit(1)

    material_counts = Counter(
        m.material_name for m in result.facade_materials if m.material_name
    )

    summary = {
        "ifc_file": ifc_path.name,
        "shell_extraction": {
            "status": "ok",
            "element_count": result.element_count,
            "vertex_count": int(result.vertices_m.shape[0]),
            "triangle_count": int(result.faces.shape[0]),
        },
        "height_analysis": {
            "elevation_m_local": result.elevation_m_local,
            "min_z_m": round(result.min_z_m, 3),
            "max_z_m": round(result.max_z_m, 3),
            "height_m": round(result.height_m, 3),
        },
        "gfa": {
            "gfa_m2": round(result.gfa_m2, 2),
        },
        "facade_materials": {
            "unique_material_count": len(material_counts),
            "materials": [
                {"name": name, "element_count": count}
                for name, count in material_counts.most_common()
            ],
        },
    }

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
