from app.clients.drive_client import drive_client
from app.core.logging import logger
import os

def upload_audio_to_drive(run_date: str, audio_content: bytes) -> str:
    filename = f"{run_date}_global-intelligence-podcast.mp3"
    tmp_path = f"/tmp/{filename}"
    
    logger.info(f"Saving temporary audio file to {tmp_path}")
    with open(tmp_path, "wb") as f:
        f.write(audio_content)
        
    logger.info(f"Uploading {filename} to Google Drive")
    try:
        file = drive_client.upload_file(tmp_path, filename, "audio/mpeg")
        file_id = file.get("id")
        return f"https://drive.google.com/file/d/{file_id}/view"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
