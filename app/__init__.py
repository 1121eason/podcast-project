import base64
import os
from pathlib import Path


def _materialize_google_credentials() -> None:
    existing = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if existing:
        print(f"[creds-shim] GOOGLE_APPLICATION_CREDENTIALS already set to {existing}, skipping", flush=True)
        return

    b64 = os.environ.get("GOOGLE_CREDENTIALS_B64")
    raw = None
    if b64:
        try:
            raw = base64.b64decode(b64).decode("utf-8")
            print(f"[creds-shim] decoded GOOGLE_CREDENTIALS_B64 → {len(raw)} bytes", flush=True)
        except Exception as e:
            print(f"[creds-shim] failed to decode GOOGLE_CREDENTIALS_B64: {e}", flush=True)
            return
    else:
        raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
        if raw:
            print(f"[creds-shim] using GOOGLE_CREDENTIALS_JSON → {len(raw)} bytes", flush=True)

    if not raw:
        print("[creds-shim] neither GOOGLE_CREDENTIALS_B64 nor GOOGLE_CREDENTIALS_JSON set, skipping", flush=True)
        return

    path = Path("/tmp/sa.json")
    path.write_text(raw, encoding="utf-8")
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(path)
    print(f"[creds-shim] wrote {len(raw)} bytes to {path}, set GOOGLE_APPLICATION_CREDENTIALS", flush=True)


_materialize_google_credentials()
