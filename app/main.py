import os
from pathlib import Path


def _materialize_credential_files() -> None:
    import logging
    logger = logging.getLogger("app.bootstrap")
    pairs = [
        ("GOOGLE_APPLICATION_CREDENTIALS_JSON", "GOOGLE_APPLICATION_CREDENTIALS"),
        ("GOOGLE_OAUTH_CLIENT_SECRET_JSON", "GOOGLE_OAUTH_CLIENT_SECRET_FILE"),
        ("GOOGLE_OAUTH_TOKEN_JSON", "GOOGLE_OAUTH_TOKEN_FILE"),
    ]
    for json_var, path_var in pairs:
        content = os.environ.get(json_var)
        target = os.environ.get(path_var)
        if not content:
            logger.info("Bootstrap skip %s: env var missing", json_var)
            continue
        if not target:
            logger.info("Bootstrap skip %s: target path env var %s missing", json_var, path_var)
            continue
        path = Path(target)
        if path.exists():
            logger.info("Bootstrap skip %s: %s already exists", json_var, target)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        logger.info("Bootstrap wrote %s -> %s (%d bytes)", json_var, target, len(content))


_materialize_credential_files()

from fastapi import FastAPI
from app.core.config import settings
from app.api import routes_briefings
from app.api import routes_signals
from app.api import routes_sources

app = FastAPI(
    title=settings.PROJECT_NAME,
    version="1.0.0",
    description="Signal Brief Pipeline API"
)

app.include_router(routes_sources.router, prefix="/sources", tags=["Sources"])
app.include_router(routes_signals.router, prefix="/signals", tags=["Signals"])
app.include_router(routes_briefings.router, tags=["Briefings"])

@app.get("/health")
def health_check():
    return {"status": "ok", "version": "1.0.0"}
