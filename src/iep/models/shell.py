from dataclasses import dataclass, field

import numpy as np
import numpy.typing as npt


@dataclass
class FacadeMaterial:
    element_global_id: str
    element_type: str
    material_name: str
    thickness_m: float | None


@dataclass
class ShellResult:
    """Output of exterior shell extraction — all coordinates in local IFC units (metres)."""

    vertices_m: npt.NDArray[np.float64]   # (N, 3) array, IFC local coords
    faces: npt.NDArray[np.int32]           # (M, 3) triangle indices
    element_count: int                     # number of exterior elements included
    elevation_m_local: float               # IfcSite.RefElevation (m above local datum)
    min_z_m: float                         # lowest vertex Z in local coords
    max_z_m: float                         # highest vertex Z in local coords
    height_m: float                        # max_z - min_z
    gfa_m2: float                          # gross floor area in m²
    facade_materials: list[FacadeMaterial] = field(default_factory=list)
