from fastapi import FastAPI
from app.core.config import settings
from app.api import routes_jobs
from app.api import routes_sources

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="全球情資日報 Podcast 自動化系統 API"
)

app.include_router(routes_jobs.router, prefix="/jobs", tags=["Jobs"])
app.include_router(routes_sources.router, prefix="/sources", tags=["Sources"])

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
