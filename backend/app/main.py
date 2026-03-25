from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.settings import settings

app = FastAPI(
    title="Vid2PDF API",
    description="API for reconstructing clean PDF pages from document screen recordings.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(router, prefix="/api")
app.mount("/artifacts", StaticFiles(directory=f"{settings.storage_path}/exports"), name="artifacts")
