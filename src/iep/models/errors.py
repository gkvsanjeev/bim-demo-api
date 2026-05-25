from pydantic import BaseModel


class StageError(BaseModel):
    stage: str
    detail: str


class IFCLoadError(Exception):
    pass


class ShellExtractionError(Exception):
    pass
