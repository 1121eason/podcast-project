from pathlib import Path

import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from app.core.config import settings

GOOGLE_WORKSPACE_SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _save_credentials(credentials: Credentials, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(credentials.to_json(), encoding="utf-8")


def _get_oauth_credentials() -> Credentials:
    token_path = Path(settings.GOOGLE_OAUTH_TOKEN_FILE)
    client_secret_path = Path(settings.GOOGLE_OAUTH_CLIENT_SECRET_FILE)
    credentials = None

    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(
            str(token_path),
            GOOGLE_WORKSPACE_SCOPES,
        )

    if credentials and credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _save_credentials(credentials, token_path)

    if credentials and credentials.valid:
        return credentials

    raise RuntimeError(
        "Google Workspace OAuth credentials are missing or invalid. "
        f"Run `python3 scripts/authorize_google_workspace.py` with "
        f"`{client_secret_path}` available to create `{token_path}`."
    )


def get_google_workspace_credentials():
    if settings.GOOGLE_WORKSPACE_AUTH_MODE.lower() == "oauth":
        return _get_oauth_credentials()

    credentials, _ = google.auth.default(scopes=GOOGLE_WORKSPACE_SCOPES)
    return credentials
