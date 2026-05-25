from fastapi import FastAPI

from iep.api.processing import router as processing_router

app = FastAPI(
    title="iEP — BIM Shell Extraction API",
    description="Extracts the exterior shell of a building from a CORENET X IFC+SG file.",
    version="0.1.0",
)

app.include_router(processing_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
