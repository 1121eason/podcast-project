from googleapiclient.discovery import build

from app.clients.google_workspace_auth import get_google_workspace_credentials
from app.core.config import settings


class SheetsClient:
    def __init__(self):
        credentials = get_google_workspace_credentials()
        self.service = build("sheets", "v4", credentials=credentials)

    def read_source_rows(self) -> list[list[str]]:
        if not settings.GOOGLE_SHEET_ID:
            raise RuntimeError("GOOGLE_SHEET_ID is required for RSS source sync.")

        result = (
            self.service.spreadsheets()
            .values()
            .get(
                spreadsheetId=settings.GOOGLE_SHEET_ID,
                range=settings.GOOGLE_SHEET_RANGE,
            )
            .execute()
        )
        return result.get("values", [])
