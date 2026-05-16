import os
from pathlib import Path


def _materialize_google_credentials() -> None:
    existing = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if existing:
        print(f"[creds-shim] GOOGLE_APPLICATION_CREDENTIALS already set to {existing}, skipping", flush=True)
        return
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not raw:
        print("[creds-shim] GOOGLE_CREDENTIALS_JSON is empty or missing, skipping", flush=True)
        return
    path = Path("/tmp/sa.json")
    path.write_text(raw, encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)
    print(f"[creds-shim] wrote {len(raw)} bytes to {path}, set GOOGLE_APPLICATION_CREDENTIALS", flush=True)


_materialize_google_credentials()
