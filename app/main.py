import os
from pathlib import Path

from fastapi import FastAPI
from app.core.config import settings
from app.api import routes_jobs
from app.api import routes_sources


def _materialize_credential_files() -> None:
    pairs = [
        ("GOOGLE_APPLICATION_CREDENTIALS_JSON", "GOOGLE_APPLICATION_CREDENTIALS"),
        ("GOOGLE_OAUTH_CLIENT_SECRET_JSON", "GOOGLE_OAUTH_CLIENT_SECRET_FILE"),
        ("GOOGLE_OAUTH_TOKEN_JSON", "GOOGLE_OAUTH_TOKEN_FILE"),
    ]
    for json_var, path_var in pairs:
        content = os.environ.get(json_var)
        target = os.environ.get(path_var)
        if not content or not target:
            continue
        path = Path(target)
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


_materialize_credential_files()

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
