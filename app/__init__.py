import os
from pathlib import Path


def _materialize_google_credentials() -> None:
    if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not raw:
        return
    path = Path("/tmp/sa.json")
    path.write_text(raw, encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)


_materialize_google_credentials()
