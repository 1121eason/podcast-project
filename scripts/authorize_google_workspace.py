from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from google_auth_oauthlib.flow import InstalledAppFlow

from app.clients.google_workspace_auth import GOOGLE_WORKSPACE_SCOPES
from app.core.config import settings


def main() -> None:
    client_secret_path = Path(settings.GOOGLE_OAUTH_CLIENT_SECRET_FILE)
    token_path = Path(settings.GOOGLE_OAUTH_TOKEN_FILE)

    if not client_secret_path.exists():
        raise SystemExit(
            f"OAuth client secret file not found: {client_secret_path}. "
            "Download an OAuth Desktop client JSON from Google Cloud Console first."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret_path),
        GOOGLE_WORKSPACE_SCOPES,
    )
    credentials = flow.run_local_server(port=0)

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")
    print(f"Saved Google Workspace OAuth token to {token_path}")


if __name__ == "__main__":
    main()
