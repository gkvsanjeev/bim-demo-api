from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from iep.api.processing import router as processing_router

app = FastAPI(
    title="iEP — BIM Shell Extraction API",
    description="Extracts the exterior shell of a building from a CORENET X IFC+SG file.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(processing_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
