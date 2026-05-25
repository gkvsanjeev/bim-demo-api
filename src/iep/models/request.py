from pydantic import BaseModel, Field


class ProcessingRequest(BaseModel):
    application_ref: str = Field(..., description="SkySAFE application reference number")
    ifc_filename: str = Field(..., description="IFC filename (file already on disk via SFTP)")


class AssessmentSelection(BaseModel):
    composite_height_template: bool = Field(True, description="Run CHT intersection check")
    ols_intersection: bool = Field(True, description="Run OLS intersection check")
    ils_technical_template: bool = Field(True, description="Run ILS technical template impact check")
    gfa: bool = Field(True, description="Run GFA limit check")
    radar: bool = Field(True, description="Run radar line-of-sight and facade reflectivity check")


class AnalysisRequest(BaseModel):
    application_ref: str = Field(..., description="SkySAFE application reference number")
    ifc_filename: str = Field(..., description="IFC filename (file already on disk via SFTP)")
    assessments: AssessmentSelection = Field(default_factory=AssessmentSelection)
