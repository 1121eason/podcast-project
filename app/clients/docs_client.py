from googleapiclient.discovery import build
from app.clients.google_workspace_auth import get_google_workspace_credentials
from app.core.config import settings
from app.core.logging import logger


def _extract_text_from_structural_elements(elements: list[dict]) -> str:
    text_parts = []
    for element in elements:
        if "paragraph" in element:
            for paragraph_element in element["paragraph"].get("elements", []):
                text_run = paragraph_element.get("textRun")
                if text_run and text_run.get("content"):
                    text_parts.append(text_run["content"])
        elif "table" in element:
            for row in element["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    text_parts.append(_extract_text_from_structural_elements(cell.get("content", [])))
        elif "tableOfContents" in element:
            text_parts.append(
                _extract_text_from_structural_elements(
                    element["tableOfContents"].get("content", [])
                )
            )
    return "".join(text_parts)


def extract_text_from_document(document: dict) -> str:
    body = document.get("body", {})
    return _extract_text_from_structural_elements(body.get("content", [])).strip()


class DocsClient:
    def __init__(self):
        try:
            credentials = get_google_workspace_credentials()
            self.service = build('docs', 'v1', credentials=credentials)
            self.drive_service = build('drive', 'v3', credentials=credentials)
        except Exception as e:
            logger.error(f"Failed to initialize Docs API client: {e}")
            self.service = None
            self.drive_service = None

    def create_document(self, title: str) -> dict:
        if not self.service:
            raise Exception("Docs API service not initialized")
        if settings.DRIVE_OUTPUT_FOLDER_ID:
            if not self.drive_service:
                raise Exception("Drive API service not initialized")
            file_metadata = {
                "name": title,
                "mimeType": "application/vnd.google-apps.document",
                "parents": [settings.DRIVE_OUTPUT_FOLDER_ID],
            }
            file = self.drive_service.files().create(
                body=file_metadata,
                fields="id",
                supportsAllDrives=True,
            ).execute()
            return {"documentId": file.get("id")}
        document = self.service.documents().create(body={"title": title}).execute()
        return {"documentId": document.get("documentId")}

    def insert_text(self, document_id: str, text: str):
        if not self.service:
            raise Exception("Docs API service not initialized")
        requests = [{"insertText": {"location": {"index": 1}, "text": text}}]
        self.service.documents().batchUpdate(documentId=document_id, body={"requests": requests}).execute()

    def get_document_text(self, document_id: str) -> str:
        if not self.service:
            raise Exception("Docs API service not initialized")
        document = self.service.documents().get(documentId=document_id).execute()
        return extract_text_from_document(document)

docs_client = DocsClient()
