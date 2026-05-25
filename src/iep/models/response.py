from pydantic import BaseModel

from iep.models.errors import StageError
from iep.models.request import AssessmentSelection


class ShellExtractionSummary(BaseModel):
    status: str
    element_count: int
    vertex_count: int
    triangle_count: int


class HeightAnalysis(BaseModel):
    elevation_m_local: float
    min_z_m: float
    max_z_m: float
    height_m: float


class GFAResult(BaseModel):
    gfa_m2: float


class MaterialEntry(BaseModel):
    name: str
    element_count: int


class FacadeMaterialSummary(BaseModel):
    unique_material_count: int
    materials: list[MaterialEntry]


class ProcessingResponse(BaseModel):
    application_ref: str
    ifc_filename: str
    shell_extraction: ShellExtractionSummary
    height_analysis: HeightAnalysis
    gfa: GFAResult
    facade_materials: FacadeMaterialSummary
    errors: list[StageError] = []


class AnalysisResponse(ProcessingResponse):
    """Extended response returned by POST /processing/analyse.

    Includes the full ProcessingResponse payload plus the PDF download URL
    and a record of which assessments were requested.
    """
    assessments_run: AssessmentSelection
    pdf_url: str
