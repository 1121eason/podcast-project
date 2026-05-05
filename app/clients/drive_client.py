from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from app.clients.google_workspace_auth import get_google_workspace_credentials
from app.core.logging import logger
from app.core.config import settings

class DriveClient:
    def __init__(self):
        try:
            credentials = get_google_workspace_credentials()
            self.service = build('drive', 'v3', credentials=credentials)
        except Exception as e:
            logger.error(f"Failed to initialize Drive API client: {e}")
            self.service = None

    def move_file_to_folder(self, file_id: str, folder_id: str):
        if not self.service:
            raise Exception("Drive API service not initialized")
        file = self.service.files().get(fileId=file_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents', []))
        self.service.files().update(
            fileId=file_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields='id, parents',
            supportsAllDrives=True
        ).execute()

    def upload_file(self, file_path: str, filename: str, mime_type: str) -> dict:
        if not self.service:
            raise Exception("Drive API service not initialized")
        file_metadata = {
            'name': filename,
            'parents': [settings.DRIVE_OUTPUT_FOLDER_ID] if settings.DRIVE_OUTPUT_FOLDER_ID else []
        }
        media = MediaFileUpload(file_path, mimetype=mime_type)
        file = self.service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id',
            supportsAllDrives=True
        ).execute()
        return file

drive_client = DriveClient()
